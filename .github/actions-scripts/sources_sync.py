"""Manifest mode of the dependency downloader.

Every entry of ``sources.json`` that is in use and to be downloaded (not ``"is-in-use":
false`` or ``"download": false``) is downloaded on each run. An archive with the SHA-256 the
manifest records is the one already installed and needs nothing. Any other is unpacked into
a temporary directory. The files it would
install are compared, byte for byte, with those already in the destination (the project's
own ``keep-files`` files excluded); the destination and the lock file are written only when they
differ, so a repackaged archive with the same files causes no change and no commit. If
only the settings changed (URL, version, unpack options) just the lock file is
updated. Changing ``version`` in the manifest therefore fetches the new release
automatically.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from archive_extract import extract_archive
from downloader_common import (
    GITHUB_OUTPUT_CHANGED,
    extract_filename,
    format_bytes,
    get_response,
    log,
    new_session,
    parse_content_length,
    sha256_file,
    write_chunks,
    write_github_outputs,
)
from sources_manifest import (
    Source,
    SourceError,
    expand_placeholders,
    load_sources,
    resolve_dest,
    update_hashes,
)
from tree_compare import tree_files

if TYPE_CHECKING:
    import argparse

# <root>/.github/actions-scripts/sources_sync.py -> <root>
DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = "data/fontsets/sources.lock.json"
LOCK_VERSION = 1

# Manifest mode identifies itself honestly: SourceForge serves its HTML project
# page, not the file, to browser-like User-Agents.
MANIFEST_USER_AGENT = (
    "debian-console-fonts-downloader/1.0 (+https://github.com/btbutts/debian-console-fonts)"
)


def use_system_trust_store() -> None:
    """Trust the operating system's CA store if ``truststore`` is installed.

    Helps on machines behind TLS-inspecting proxies whose CA lives in the OS
    keychain. Without the package, requests keeps using its bundled CAs.
    """
    if importlib.util.find_spec("truststore") is None:
        return
    importlib.import_module("truststore").inject_into_ssl()
    log("TLS trust          : operating system store (truststore)")


def load_lock(path: Path) -> dict:
    """Return the lock file contents, or an empty lock if there is none."""
    if not path.is_file():
        return {"lock_version": LOCK_VERSION, "sources": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        message = f"lock file {path} is not valid JSON: {exc}"
        raise SourceError(message) from exc
    if not isinstance(data, dict) or not isinstance(data.get("sources"), dict):
        message = f"lock file {path} has an unexpected format"
        raise SourceError(message)
    return data


def save_lock(path: Path, lock: dict) -> None:
    """Write the lock file deterministically (sorted keys, no timestamps)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    part.replace(path)


def fetch_archive(url: str, archive: Path, user_agent: str | None = None) -> str:
    """Download *url* to *archive* and return its SHA-256."""
    with new_session() as session:
        session.headers["User-Agent"] = user_agent or MANIFEST_USER_AGENT
        with get_response(session, url) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type.startswith("text/html") and not url.lower().endswith((".html", ".htm")):
                message = (
                    f"the server returned an HTML page ({response.url}) instead of an "
                    "archive; a proxy or filter may be blocking this client, or the "
                    "site rejects this User-Agent (see the 'user-agent' key)"
                )
                raise SourceError(message)
            remote_size = parse_content_length(response.headers)
            if remote_size is None:
                log("Remote size        : unknown (no Content-Length)")
            else:
                log(f"Remote size        : {format_bytes(remote_size)} ({remote_size} bytes)")
            write_chunks(response, archive, remote_size)
    return sha256_file(archive)


def _lock_record(source: Source, url: str, digest: str) -> dict:
    """Return what the lock file stores for *source* downloaded from *url*."""
    return {
        "dest": source.dest,
        "include": list(source.unpack.include),
        "sha256": digest,
        "strip_components": source.unpack.strip_components,
        "url": url,
        "version": source.version,
    }


def _warn_dangling_symlinks(tree: Path) -> None:
    """Log symlinks in *tree* whose target was not extracted."""
    for link in sorted(tree.rglob("*")):
        if link.is_symlink() and not link.exists():
            log(
                f"warning: dangling symlink {link.relative_to(tree)} -> "
                f"{link.readlink()} (its target was not extracted; check 'include')"
            )


def _remove(path: Path) -> None:
    """Delete *path* whether it is a directory, a file or a symlink."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _carry_over(source: Source, dest: Path, staging: Path) -> None:
    """Copy the project's own files (the ``keep-files`` list) from the old tree into *staging*."""
    for name in source.unpack.keep:
        old = dest / name
        if old.is_file():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(old, target)


def _fill(source: Source, archive: Path, staging: Path, dest: Path) -> int:
    """Unpack *archive* into the empty directory *staging*; return the number of files."""
    count = extract_archive(archive, staging, source.unpack.strip_components, source.unpack.include)
    if count == 0:
        message = f"source {source.name!r}: no files matched; refusing to replace {dest}"
        raise SourceError(message)
    if source.unpack.keep_archive:
        (staging / ".archive").mkdir()
        shutil.copyfile(archive, staging / ".archive" / archive.name)
    return count


def _unpack(source: Source, archive: Path, dest: Path) -> tuple[Path, int]:
    """Unpack *archive* into a staging directory next to *dest*; return it and the file count."""
    staging = dest.parent / f".{dest.name}.new-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        count = _fill(source, archive, staging, dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return staging, count


def _same_files(source: Source, staging: Path, dest: Path) -> bool:
    """Return True if *dest* already holds exactly the files in *staging*.

    The project's own files (the ``keep-files`` list) are not compared.
    """
    if not dest.is_dir():
        return False
    ignore = set(source.unpack.keep)
    return tree_files(staging, ignore) == tree_files(dest, ignore)


def _swap_in(source: Source, staging: Path, dest: Path) -> None:
    """Replace *dest* with *staging*, carrying the project's own files across."""
    _carry_over(source, dest, staging)
    _warn_dangling_symlinks(staging)
    _remove(dest)
    staging.replace(dest)


def _settings(record: dict) -> dict:
    """Return the part of a lock record that does not depend on the archive's exact bytes."""
    return {key: value for key, value in record.items() if key != "sha256"}


def _identical_files(lock: dict, name: str, record: dict) -> str:
    """Handle a download whose files match what we have; touch the lock only if settings changed."""
    previous = lock["sources"].get(name)
    if previous is not None and _settings(previous) == _settings(record):
        log("Result             : unchanged (the files are identical; nothing written)")
        return "unchanged"
    lock["sources"][name] = record
    log("Result             : lock updated (the files are identical; only the settings changed)")
    return "relocked"


def _url_and_filename(source: Source) -> tuple[str, str]:
    """Return the real download URL of *source* and the file name to store it under."""
    label = f"source {source.name!r}"
    url = expand_placeholders(source.url, source.version, label)
    if source.fetch.filename:
        return url, expand_placeholders(source.fetch.filename, source.version, label)
    return url, extract_filename(url)


def _already_installed(source: Source, lock: dict, record: dict, dest: Path) -> bool:
    """Return True if the download is the archive that is installed, so nothing is to be done.

    That is so when its SHA-256 is the one in the manifest, the files are there, and the
    settings they were unpacked with are the current ones. (The SHA-256 says only that the
    archive is the same file, not that it was unpacked the way the manifest now asks.)
    """
    if source.fetch.sha256 != record["sha256"] or not dest.is_dir():
        return False
    previous = lock["sources"].get(source.name)
    return previous is not None and _settings(previous) == _settings(record)


def process_source(
    source: Source, root: Path, lock: dict, workdir: Path, *, force: bool = False
) -> str:
    """Fetch and unpack one source. Returns 'created', 'updated', 'relocked' or 'unchanged'."""
    url, filename = _url_and_filename(source)
    dest = resolve_dest(root, source.dest)

    log(f"--- {source.name}")
    log(f"URL                : {url}")
    log(f"Version            : {source.version or '(unversioned)'}")
    log(f"Destination        : {dest}")

    archive = workdir / source.name / Path(filename).name
    archive.parent.mkdir(parents=True, exist_ok=True)
    digest = fetch_archive(url, archive, source.fetch.user_agent)
    log(f"Archive SHA-256    : {digest}")

    record = _lock_record(source, url, digest)
    if not force and _already_installed(source, lock, record, dest):
        log("Result             : unchanged (SHA-256 as in the manifest; nothing to do)")
        return "unchanged"
    staging, count = _unpack(source, archive, dest)
    try:
        if not force and _same_files(source, staging, dest):
            return _identical_files(lock, source.name, record)
        status = "updated" if source.name in lock["sources"] and dest.exists() else "created"
        _swap_in(source, staging, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    lock["sources"][source.name] = record
    log(f"Result             : {status} ({count} files)")
    return status


def _under(root: Path, path: str) -> Path:
    """Return *path* as given if absolute, otherwise relative to *root*."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def _select(sources: list[Source], only: list[str]) -> list[Source]:
    """Return the sources to download, limited to the names in *only* if any are given."""
    enabled = [source for source in sources if source.enabled and source.fetch.download]
    unknown = sorted(set(only) - {source.name for source in enabled})
    if unknown:
        message = f"--only names not in the manifest (or disabled, or not downloaded): {unknown}"
        raise SourceError(message)
    return [source for source in enabled if not only or source.name in only]


def _sync(
    sources: list[Source], root: Path, lock: dict, *, force: bool
) -> tuple[list[str], list[str]]:
    """Process every source; return the names that changed and the names that failed."""
    changed: list[str] = []
    failed: list[str] = []
    with tempfile.TemporaryDirectory(prefix="sources-") as tmp:
        for source in sources:
            try:
                result = process_source(source, root, lock, Path(tmp), force=force)
            except (
                SourceError,
                requests.RequestException,
                OSError,
                tarfile.TarError,
                zipfile.BadZipFile,
            ) as exc:
                print(f"error: {source.name}: {exc}", file=sys.stderr)
                failed.append(source.name)
                continue
            if result != "unchanged":
                changed.append(source.name)
    return changed, failed


def run_sources(args: argparse.Namespace) -> int:
    """Process the manifest named by ``--sources``; return the exit status."""
    use_system_trust_store()
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    manifest = _under(root, args.sources)
    lock_path = _under(root, args.lock)

    log(f"Repository root    : {root}")
    log(f"Manifest           : {manifest}")
    try:
        sources = _select(load_sources(manifest), args.only)
        lock = load_lock(lock_path)
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    changed, failed = _sync(sources, root, lock, force=args.force)
    if changed:
        save_lock(lock_path, lock)
        log(f"Lock file          : updated {lock_path}")
        update_hashes(manifest, {name: lock["sources"][name]["sha256"] for name in changed})
        log(f"Manifest           : SHA-256 of {', '.join(changed)} updated")
    write_github_outputs(
        {
            GITHUB_OUTPUT_CHANGED: "true" if changed else "false",
            "changed_sources": ",".join(changed),
            "failed_sources": ",".join(failed),
        }
    )
    log(f"Summary            : changed={changed or 'none'} failed={failed or 'none'}")
    return 1 if failed else 0

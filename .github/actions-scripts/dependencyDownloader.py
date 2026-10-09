#!/usr/bin/env python3
"""Download remote files, either one URL at a time or a whole manifest.

Single-file mode (unchanged from OpenWRT-BuildEnv's copy)::

    python3 dependencyDownloader.py <url> <output-dir>

Relative output paths are resolved from this script's directory. The stored
filename is taken from the URL (right-to-left until '/', '=', or an invalid
filename character). An existing file is overwritten only when its SHA-256
differs from the freshly downloaded copy.

Manifest mode::

    python3 .github/actions-scripts/dependencyDownloader.py --sources sources.json

``sources.json`` lists archives to fetch and unpack. Each entry has:

    name              unique name (also the key in the lock file)
    url               download URL; may use {version} {major} {minor} {patch}
                      {major_minor}, filled in from ``version``
    dest              directory the archive is unpacked into, relative to the
                      repository root; its previous contents are replaced
    version           optional; required only if the URL uses a placeholder
    filename          optional; defaults to the last segment of the URL
    strip_components  optional, leading path parts removed from archive members
    include           optional list of globs (relative to the stripped root);
                      only matching files are kept
    enabled           optional, default true; false entries are ignored
    keep_archive      optional, default false; also keep the downloaded archive
    user_agent        optional; overrides the default manifest-mode User-Agent

Every entry is downloaded each run. Its archive SHA-256, resolved URL, version
and unpack options are compared with ``sources/sources.lock.json``; ``dest`` is
rewritten only when something differs or ``dest`` is missing. Changing
``version`` in the manifest therefore fetches the new release automatically.

When running in GitHub Actions, the step output ``changed`` is written to
``$GITHUB_OUTPUT`` as ``true`` if anything was created or replaced and
``false`` otherwise. Manifest mode also writes ``changed_sources`` and
``failed_sources`` (comma-separated names).

"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import zipfile
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
# <root>/.github/actions-scripts/this_script.py -> <root>
DEFAULT_ROOT = SCRIPT_DIR.parents[1] if len(SCRIPT_DIR.parents) > 1 else SCRIPT_DIR
DEFAULT_LOCK = "sources/sources.lock.json"

MEMORY_LIMIT_BYTES = 250 * 1024 * 1024  # 250 MiB
CHUNK_SIZE = 8192
HTTP_TIMEOUT_SECONDS = 120
GITHUB_OUTPUT_CHANGED = "changed"

# Characters that terminate the filename scan. Includes path/query
# delimiters plus characters illegal in Windows, macOS, or Linux names.
_INVALID_FILENAME_CHARS = set('<>:"/\\|?*=' + "".join(chr(i) for i in range(32)))

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.4196.66 Safari/537.36 Edg/152.0.4196.66"
)

_REQUEST_HEADERS = {
    "User-Agent": _USER_AGENT,
    # Identity so Content-Length matches the bytes we hash/write. requests
    # would otherwise advertise gzip and decompress, making the header lie.
    "Accept-Encoding": "identity",
}

_MIB = 1024 * 1024

# Manifest mode identifies itself honestly: SourceForge serves its HTML project
# page, not the file, to browser-like User-Agents.
MANIFEST_USER_AGENT = (
    "debian-console-fonts-downloader/1.0 "
    "(+https://github.com/btbutts/debian-console-fonts)"
)


def extract_filename(url: str) -> str:
    """Return the filename at the end of *url*.

    Characters are collected from the right until the first '/', '=', or
    any character that is not legal in a Windows/macOS/Linux filename.
    Percent-encoded sequences are decoded afterwards.
    """
    collected: list[str] = []
    for char in reversed(url.rstrip()):
        if char in _INVALID_FILENAME_CHARS:
            break
        collected.append(char)

    filename = unquote("".join(reversed(collected))).rstrip(" .")
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise ValueError(
            f"could not extract a valid filename from URL: {url!r}"
        )
    return filename


def resolve_output_dir(output_arg: str) -> Path:
    """Resolve *output_arg* relative to the script directory, then to absolute."""
    return (SCRIPT_DIR / output_arg).resolve()


def format_bytes(num_bytes: int) -> str:
    """Return *num_bytes* as a human-readable size string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    for unit, size in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024)):
        if num_bytes >= size:
            return f"{num_bytes / size:.2f} {unit}"
    return f"{num_bytes} B"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest for a file at *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_buffer(buffer: io.BytesIO) -> str:
    """Return the SHA-256 hex digest for the current contents of *buffer*."""
    digest = hashlib.sha256()
    buffer.seek(0)
    while True:
        chunk = buffer.read(CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
    buffer.seek(0)
    return digest.hexdigest()


def parse_content_length(headers) -> int | None:
    """Return the parsed Content-Length value, or None if unavailable."""
    raw = headers.get("Content-Length")
    if raw is None or raw == "":
        return None
    try:
        length = int(raw)
    except (TypeError, ValueError):
        return None
    if length < 0:
        return None
    return length


def write_github_outputs(values: dict[str, str]) -> None:
    """Append step outputs when running under GitHub Actions.

    No-op locally: ``GITHUB_OUTPUT`` is only set inside a workflow step.
    Values are strings; booleans are the lowercase ``true`` / ``false`` that
    Actions ``if:`` expressions compare against.
    """
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")
            log(f"GitHub output      : {key}={value}")


def write_github_output(changed: bool) -> None:
    """Append the ``changed`` step output (single-file mode)."""
    write_github_outputs({GITHUB_OUTPUT_CHANGED: "true" if changed else "false"})


class ProgressMeter:
    """Redraw a two-line stderr block with download / hash progress.

    Uses ANSI cursor-up so the meter occupies a fixed terminal block
    instead of scrolling (wget/curl style). In streaming SHA-256 mode
    the total chunk count is ceil(Content-Length / CHUNK_SIZE).
    """

    _LABEL = "Downloading        :"  # 19 chars; chunk line is indented to match

    def __init__(
        self,
        total_bytes: int | None,
        chunk_size: int,
        show_chunks: bool,
    ) -> None:
        self.total_bytes = total_bytes
        self.chunk_size = chunk_size
        self.show_chunks = show_chunks
        self.bytes_done = 0
        self.chunks_done = 0
        if total_bytes is None:
            self.total_chunks: int | None = None
        else:
            self.total_chunks = (total_bytes + chunk_size - 1) // chunk_size
        self._last_draw = 0.0
        self._nlines = 0
        self._drawn = False

    def update(self, nbytes: int) -> None:
        """Account for one received chunk and redraw at ~20 Hz."""
        self.bytes_done += nbytes
        self.chunks_done += 1
        now = time.monotonic()
        if now - self._last_draw < 0.05:
            return
        self._draw()
        self._last_draw = now

    def close(self) -> None:
        """Force a final draw, leaving the cursor on the line below the meter."""
        self._draw()

    def _render_lines(self) -> list[str]:
        downloaded = self.bytes_done / _MIB
        indent = " " * len(self._LABEL)
        if self.total_bytes is not None:
            total = self.total_bytes / _MIB
            pct = (
                100.0 * self.bytes_done / self.total_bytes
                if self.total_bytes
                else 100.0
            )
            lines = [
                f"{self._LABEL}{downloaded:7.2f}  /  {total:7.2f} MiB ({pct:.1f}%)"
            ]
        else:
            lines = [f"{self._LABEL}{downloaded:7.2f} MiB"]

        if not self.show_chunks:
            return lines

        if self.total_chunks is not None:
            lines.append(
                f"{indent}{self.chunks_done:7d}  /  {self.total_chunks:7d} "
                "total chunks hashed"
            )
        else:
            lines.append(f"{indent}{self.chunks_done:7d} chunks hashed")
        return lines

    def _draw(self) -> None:
        lines = self._render_lines()
        if self._drawn and self._nlines:
            sys.stderr.write(f"\033[{self._nlines}A")
        for line in lines:
            sys.stderr.write("\r\033[2K" + line + "\n")
        sys.stderr.flush()
        self._nlines = len(lines)
        self._drawn = True


def consume_chunks(
    response: requests.Response,
    total_bytes: int | None,
    show_chunks: bool,
    on_chunk,
) -> None:
    """Feed each response body chunk to *on_chunk* while updating progress."""
    meter = ProgressMeter(total_bytes, CHUNK_SIZE, show_chunks)
    try:
        for chunk in iter_chunks(response):
            on_chunk(chunk)
            meter.update(len(chunk))
    finally:
        meter.close()


def new_session() -> requests.Session:
    """Create a preconfigured session for dependency downloads."""
    session = requests.Session()
    session.headers.update(_REQUEST_HEADERS)
    return session


def get_response(session: requests.Session, url: str) -> requests.Response:
    """Fetch a URL as a streamed response and fail fast on HTTP errors."""
    response = session.get(url, stream=True, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response


def iter_chunks(response: requests.Response, chunk_size: int = CHUNK_SIZE):
    """Yield non-empty content chunks from a streamed HTTP response."""
    for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:  # drop keep-alive padding
            yield chunk


def write_chunks(
    response: requests.Response,
    dest: Path,
    total_bytes: int | None = None,
) -> None:
    """Stream *response* to *dest* via a sibling .part file, then replace."""
    part_path = dest.with_name(dest.name + ".part")
    try:
        with part_path.open("wb") as handle:
            consume_chunks(response, total_bytes, False, handle.write)
        part_path.replace(dest)
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise


def write_buffer(buffer: io.BytesIO, dest: Path) -> None:
    """
    Write buffer contents to output dir via
    a sibling .part file, then replace.
    """
    part_path = dest.with_name(dest.name + ".part")
    try:
        buffer.seek(0)
        with part_path.open("wb") as handle:
            handle.write(buffer.getbuffer())
        part_path.replace(dest)
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise


def read_into_buffer(
    response: requests.Response,
    total_bytes: int | None = None,
) -> io.BytesIO:
    """Download a response body into an in-memory buffer with progress."""
    buffer = io.BytesIO()
    consume_chunks(response, total_bytes, False, buffer.write)
    buffer.seek(0)
    return buffer


def stream_hash(
    response: requests.Response,
    total_bytes: int | None = None,
) -> str:
    """Return the SHA-256 hash of a streamed response body."""
    digest = hashlib.sha256()
    consume_chunks(response, total_bytes, True, digest.update)
    return digest.hexdigest()


def log(message: str) -> None:
    """Print a message to stdout."""
    print(message, flush=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the dependency downloader."""
    parser = argparse.ArgumentParser(
        description=(
            "Download a URL into an output directory resolved relative to this "
            "script's directory (overwriting only when sha256sum differs), or "
            "fetch and unpack every source listed in a JSON manifest (--sources)."
        )
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="Remote URL. The filename is taken from the end of this URL.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output directory, relative to this script's directory.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_flag",
        default=None,
        metavar="DIR",
        help="Output directory (alternative to the positional argument).",
    )
    parser.add_argument(
        "--sources",
        metavar="FILE",
        default=None,
        help="JSON manifest of archives to download and unpack "
        "(path relative to --root unless absolute).",
    )
    parser.add_argument(
        "--root",
        metavar="DIR",
        default=None,
        help="Repository root that manifest paths are relative to "
        f"(default: {DEFAULT_ROOT}).",
    )
    parser.add_argument(
        "--lock",
        metavar="FILE",
        default=DEFAULT_LOCK,
        help=f"Lock file, relative to --root (default: {DEFAULT_LOCK}).",
    )
    parser.add_argument(
        "--only",
        metavar="NAME",
        action="append",
        default=[],
        help="Only process this manifest entry (repeatable).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract every selected entry even if the lock matches.",
    )
    args = parser.parse_args(argv)

    if args.sources:
        if args.url or args.output or args.output_flag:
            parser.error("--sources cannot be combined with a URL or output directory")
        args.output_dir = None
        return args

    if args.only or args.force or args.root:
        parser.error("--only, --force and --root need --sources")
    if not args.url:
        parser.error("a URL is required (or use --sources FILE)")
    output_dir = args.output_flag or args.output
    if not output_dir:
        parser.error(
            "an output directory is required "
            "(positional argument or -o/--output)"
        )
    if args.output_flag and args.output:
        parser.error(
            "provide the output directory as a positional argument "
            "or as -o/--output, not both"
        )
    args.output_dir = output_dir
    return args


def download(url: str, dest: Path) -> str:
    """Download *url* to *dest*.

    Returns one of: 'created', 'updated', 'unchanged'.
    """
    local_exists = dest.is_file()
    log(f"Local file exists  : {local_exists}")

    executor: ThreadPoolExecutor | None = None
    local_hash_future: Future[str] | None = None
    if local_exists:
        executor = ThreadPoolExecutor(max_workers=1)
        local_hash_future = executor.submit(sha256_file, dest)

    try:
        with new_session() as session:
            with get_response(session, url) as response:
                remote_size = parse_content_length(response.headers)
                if remote_size is None:
                    log("Remote size        : unknown (no Content-Length); streaming")
                    use_memory = False
                else:
                    log(
                        f"Remote size        : {format_bytes(remote_size)} "
                        f"({remote_size} bytes)"
                    )
                    use_memory = remote_size <= MEMORY_LIMIT_BYTES

                if use_memory:
                    log(
                        f"Transfer mode      : in-memory "
                        f"(<= {format_bytes(MEMORY_LIMIT_BYTES)})"
                    )
                    buffer = read_into_buffer(response, remote_size)
                else:
                    log("Transfer mode      : streaming (chunked SHA-256)")
                    buffer = None

                if not local_exists:
                    if buffer is not None:
                        write_buffer(buffer, dest)
                        buffer.close()
                    else:
                        write_chunks(response, dest, remote_size)
                    return "created"

                # Local copy exists: compare SHA-256 before writing.
                if buffer is not None:
                    remote_hash = sha256_buffer(buffer)
                else:
                    remote_hash = stream_hash(response, remote_size)

                assert local_hash_future is not None
                local_hash = local_hash_future.result()
                log(f"Remote SHA-256     : {remote_hash}")
                log(f"Local  SHA-256     : {local_hash}")

                if remote_hash == local_hash:
                    if buffer is not None:
                        buffer.close()
                    return "unchanged"

                if buffer is not None:
                    write_buffer(buffer, dest)
                    buffer.close()
                    return "updated"

            # Streaming path, hashes differed: the first response body was
            # consumed for hashing, so fetch again and write directly.
            log("SHA-256 mismatch   : re-downloading to overwrite local copy")
            with get_response(session, url) as response:
                remote_size = parse_content_length(response.headers)
                write_chunks(response, dest, remote_size)
            return "updated"
    finally:
        if executor is not None:
            executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Manifest mode (--sources)
# ---------------------------------------------------------------------------

_SOURCE_KEYS = {
    "name",
    "url",
    "dest",
    "version",
    "filename",
    "strip_components",
    "include",
    "enabled",
    "keep_archive",
    "user_agent",
}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


class SourceError(Exception):
    """A manifest entry is invalid or its archive cannot be used."""


@dataclass(frozen=True)
class Source:
    """One entry of the sources manifest."""

    name: str
    url: str
    dest: str
    version: str | None = None
    filename: str | None = None
    strip_components: int = 0
    include: tuple[str, ...] = ()
    enabled: bool = True
    keep_archive: bool = False
    user_agent: str | None = None


def _require_type(entry: dict, key: str, kind: type, label: str) -> None:
    if key in entry and not isinstance(entry[key], kind):
        raise SourceError(f"{label}: '{key}' must be {kind.__name__}")


def load_sources(path: Path) -> list[Source]:
    """Read and validate the manifest at *path*."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SourceError(f"cannot read manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SourceError(f"manifest {path} is not valid JSON: {exc}") from exc

    entries = data.get("sources") if isinstance(data, dict) else data
    if not isinstance(entries, list) or not entries:
        raise SourceError("manifest must be a non-empty list (or {\"sources\": [...]})")

    sources: list[Source] = []
    for index, entry in enumerate(entries):
        label = f"entry {index + 1}"
        if not isinstance(entry, dict):
            raise SourceError(f"{label}: must be an object")
        label = f"entry {entry.get('name', index + 1)!r}"
        unknown = set(entry) - _SOURCE_KEYS
        if unknown:
            raise SourceError(f"{label}: unknown keys {sorted(unknown)}")
        for key in ("name", "url", "dest"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise SourceError(f"{label}: '{key}' is required and must be a string")
        if not _NAME_RE.match(entry["name"]):
            raise SourceError(f"{label}: name may only use letters, digits, '.', '_' and '-'")
        for key in ("version", "filename", "user_agent"):
            if key in entry and entry[key] is not None:
                _require_type(entry, key, str, label)
        _require_type(entry, "strip_components", int, label)
        if isinstance(entry.get("strip_components"), bool) or entry.get("strip_components", 0) < 0:
            raise SourceError(f"{label}: 'strip_components' must be an integer >= 0")
        for key in ("enabled", "keep_archive"):
            _require_type(entry, key, bool, label)
        include = entry.get("include", [])
        if not isinstance(include, list) or not all(isinstance(g, str) and g for g in include):
            raise SourceError(f"{label}: 'include' must be a list of non-empty strings")

        dest = posixpath.normpath(entry["dest"].replace("\\", "/"))
        if dest in {".", ""} or dest.startswith(("/", "..")) or re.match(r"^[A-Za-z]:", dest):
            raise SourceError(f"{label}: 'dest' must be a relative path inside the repository")
        sources.append(
            Source(
                name=entry["name"],
                url=entry["url"].strip(),
                dest=dest,
                version=entry.get("version"),
                filename=entry.get("filename"),
                strip_components=entry.get("strip_components", 0),
                include=tuple(include),
                enabled=entry.get("enabled", True),
                keep_archive=entry.get("keep_archive", False),
                user_agent=entry.get("user_agent"),
            )
        )

    names = [s.name for s in sources]
    if len(set(names)) != len(names):
        raise SourceError("manifest has duplicate names")
    for first in sources:
        for second in sources:
            if first is not second and (
                first.dest == second.dest or second.dest.startswith(first.dest + "/")
            ):
                raise SourceError(
                    f"'dest' of {second.name!r} is the same as or inside that of {first.name!r}"
                )
    return sources


def version_fields(version: str) -> dict[str, str]:
    """Return the placeholder values derived from *version*."""
    fields = {"version": version}
    match = _VERSION_RE.match(version)
    if match:
        major, minor, patch = match.groups()
        fields["major"] = major
        if minor is not None:
            fields["minor"] = minor
            fields["major_minor"] = f"{major}.{minor}"
        if patch is not None:
            fields["patch"] = patch
    return fields


def expand_placeholders(template: str, version: str | None, label: str) -> str:
    """Fill {version}-style placeholders in *template*; fail on unknown ones."""
    if not _PLACEHOLDER_RE.search(template):
        return template
    if version is None:
        raise SourceError(f"{label}: uses a {{placeholder}} but has no 'version'")
    fields = version_fields(version)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in fields:
            raise SourceError(
                f"{label}: placeholder {{{key}}} is not available for version {version!r}"
            )
        return fields[key]

    return _PLACEHOLDER_RE.sub(replace, template)


def resolve_dest(root: Path, dest: str) -> Path:
    """Return the absolute *dest* below *root*, refusing anything that escapes."""
    root = root.resolve()
    path = (root / dest).resolve()
    if path == root or root not in path.parents:
        raise SourceError(f"destination {dest!r} is outside the repository")
    return path


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob (``*``, ``?``, ``**``) into a full-match regex."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _matches(rel: str, patterns: list[tuple[str, re.Pattern[str]]]) -> bool:
    """True if *rel* matches a pattern, or sits below a literal directory pattern."""
    if not patterns:
        return True
    for raw, regex in patterns:
        if regex.match(rel):
            return True
        if not any(c in raw for c in "*?") and rel.startswith(raw.rstrip("/") + "/"):
            return True
    return False


def _member_path(name: str, strip: int) -> str | None:
    """Return the cleaned in-archive path after stripping, or None to skip it."""
    posix = name.replace("\\", "/")
    if posix.startswith("/") or re.match(r"^[A-Za-z]:", posix):
        raise SourceError(f"unsafe absolute path in archive: {name!r}")
    parts = [part for part in posix.split("/") if part not in {"", "."}]
    if ".." in parts:
        raise SourceError(f"unsafe path in archive: {name!r}")
    parts = parts[strip:]
    return "/".join(parts) if parts else None


def _check_symlink(rel: str, target: str) -> None:
    """Refuse symlinks that point outside the extracted tree."""
    if target.startswith("/") or re.match(r"^[A-Za-z]:", target):
        raise SourceError(f"unsafe absolute symlink in archive: {rel!r} -> {target!r}")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
    if resolved == ".." or resolved.startswith("../"):
        raise SourceError(f"symlink escapes the archive: {rel!r} -> {target!r}")


def _place(staging: Path, rel: str) -> Path:
    """Return the path for *rel* inside *staging*, creating its parent directory."""
    target = staging / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def extract_archive(
    archive: Path,
    staging: Path,
    strip_components: int = 0,
    include: tuple[str, ...] = (),
) -> int:
    """Unpack a tar or zip *archive* into *staging*; return the number of entries."""
    patterns = [(glob, _glob_to_regex(glob)) for glob in include]
    count = 0
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive, "r:*") as tar:
            for member in tar:
                rel = _member_path(member.name, strip_components)
                if rel is None or member.isdir() or not _matches(rel, patterns):
                    continue
                if member.issym():
                    _check_symlink(rel, member.linkname)
                    target = _place(staging, rel)
                    os.symlink(member.linkname, target)
                elif member.isfile() or member.islnk():
                    source = tar.extractfile(member)
                    if source is None:
                        continue
                    target = _place(staging, rel)
                    with source, target.open("wb") as handle:
                        shutil.copyfileobj(source, handle)
                    target.chmod(0o755 if member.mode & 0o111 else 0o644)
                else:
                    log(f"Skipping special file in archive: {member.name}")
                    continue
                count += 1
    elif zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                rel = _member_path(info.filename, strip_components)
                if rel is None or info.is_dir() or not _matches(rel, patterns):
                    continue
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    link = bundle.read(info).decode("utf-8")
                    _check_symlink(rel, link)
                    os.symlink(link, _place(staging, rel))
                else:
                    target = _place(staging, rel)
                    with bundle.open(info) as source, target.open("wb") as handle:
                        shutil.copyfileobj(source, handle)
                    target.chmod(0o755 if mode & 0o111 else 0o644)
                count += 1
    else:
        raise SourceError(f"{archive.name} is not a tar or zip archive")
    return count


def load_lock(path: Path) -> dict:
    """Return the lock file contents, or an empty lock if there is none."""
    if not path.is_file():
        return {"lock_version": 1, "sources": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceError(f"lock file {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("sources"), dict):
        raise SourceError(f"lock file {path} has an unexpected format")
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
                raise SourceError(
                    f"the server returned an HTML page ({response.url}) instead of an "
                    "archive; a proxy or filter may be blocking this client, or the "
                    "site rejects this User-Agent (see the 'user_agent' key)"
                )
            remote_size = parse_content_length(response.headers)
            if remote_size is None:
                log("Remote size        : unknown (no Content-Length)")
            else:
                log(f"Remote size        : {format_bytes(remote_size)} ({remote_size} bytes)")
            write_chunks(response, archive, remote_size)
    return sha256_file(archive)


def process_source(source: Source, root: Path, lock: dict, workdir: Path, force: bool) -> str:
    """Fetch and unpack one source. Returns 'created', 'updated' or 'unchanged'."""
    label = f"source {source.name!r}"
    url = expand_placeholders(source.url, source.version, label)
    filename = (
        expand_placeholders(source.filename, source.version, label)
        if source.filename
        else extract_filename(url)
    )
    dest = resolve_dest(root, source.dest)

    log(f"--- {source.name}")
    log(f"URL                : {url}")
    log(f"Version            : {source.version or '(unversioned)'}")
    log(f"Destination        : {dest}")

    archive = workdir / source.name / Path(filename).name
    archive.parent.mkdir(parents=True, exist_ok=True)
    digest = fetch_archive(url, archive, source.user_agent)
    log(f"Archive SHA-256    : {digest}")

    record = {
        "dest": source.dest,
        "include": list(source.include),
        "sha256": digest,
        "strip_components": source.strip_components,
        "url": url,
        "version": source.version,
    }
    previous = lock["sources"].get(source.name)
    populated = dest.is_dir() and any(dest.iterdir())
    if not force and populated and previous == record:
        log("Result             : unchanged (lock matches; download discarded)")
        return "unchanged"

    status = "updated" if previous is not None and dest.exists() else "created"
    staging = dest.parent / f".{dest.name}.new-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        count = extract_archive(archive, staging, source.strip_components, source.include)
        if count == 0:
            raise SourceError(f"{label}: no files matched; refusing to replace {source.dest}")
        for link in sorted(staging.rglob("*")):
            if link.is_symlink() and not link.exists():
                log(
                    f"warning: dangling symlink {link.relative_to(staging)} -> "
                    f"{os.readlink(link)} (its target was not extracted; check 'include')"
                )
        if source.keep_archive:
            keep = staging / ".archive"
            keep.mkdir()
            shutil.copyfile(archive, keep / Path(filename).name)
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        elif dest.exists() or dest.is_symlink():
            dest.unlink()
        os.replace(staging, dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    lock["sources"][source.name] = record
    log(f"Result             : {status} ({count} files)")
    return status


def run_sources(args: argparse.Namespace) -> int:
    """Process the manifest named by ``--sources``; return the exit status."""
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    manifest = Path(args.sources)
    if not manifest.is_absolute():
        manifest = root / manifest
    lock_path = Path(args.lock)
    if not lock_path.is_absolute():
        lock_path = root / lock_path

    log(f"Repository root    : {root}")
    log(f"Manifest           : {manifest}")
    try:
        sources = [s for s in load_sources(manifest) if s.enabled]
        known = {s.name for s in sources}
        missing = sorted(set(args.only) - known)
        if missing:
            raise SourceError(f"--only names not in the manifest (or disabled): {missing}")
        lock = load_lock(lock_path)
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.only:
        sources = [s for s in sources if s.name in set(args.only)]

    changed: list[str] = []
    failed: list[str] = []
    with tempfile.TemporaryDirectory(prefix="sources-") as tmp:
        for source in sources:
            try:
                result = process_source(source, root, lock, Path(tmp), args.force)
            except (SourceError, requests.RequestException, OSError,
                    tarfile.TarError, zipfile.BadZipFile) as exc:
                print(f"error: {source.name}: {exc}", file=sys.stderr)
                failed.append(source.name)
                continue
            if result != "unchanged":
                changed.append(source.name)

    if changed:
        save_lock(lock_path, lock)
        log(f"Lock file          : updated {lock_path}")
    write_github_outputs(
        {
            GITHUB_OUTPUT_CHANGED: "true" if changed else "false",
            "changed_sources": ",".join(changed),
            "failed_sources": ",".join(failed),
        }
    )
    log(f"Summary            : changed={changed or 'none'} failed={failed or 'none'}")
    return 1 if failed else 0


def use_system_trust_store() -> None:
    """Trust the operating system's CA store if ``truststore`` is installed.

    Helps on machines behind TLS-inspecting proxies whose CA lives in the OS
    keychain. Without the package, requests keeps using its bundled CAs.
    """
    try:
        import truststore  # type: ignore[import-not-found]
    except ImportError:
        return
    truststore.inject_into_ssl()
    log("TLS trust          : operating system store (truststore)")


def main(argv: list[str] | None = None) -> int:
    """Run the dependency downloader CLI."""
    args = parse_args(argv)
    if args.sources:
        use_system_trust_store()

    if args.sources:
        return run_sources(args)

    try:
        filename = extract_filename(args.url)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output_dir = resolve_output_dir(args.output_dir)
    dest = output_dir / filename

    log(f"Script directory   : {SCRIPT_DIR}")
    log(f"Output directory   : {output_dir}")
    log(f"URL                : {args.url}")
    log(f"Filename           : {filename}")
    log(f"Destination        : {dest}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"error: cannot create output directory {output_dir}: {exc}", file=sys.stderr)
        return 1

    if dest.exists() and not dest.is_file():
        print(
            f"error: destination exists and is not a regular file: {dest}",
            file=sys.stderr,
        )
        return 1

    try:
        result = download(args.url, dest)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        reason = exc.response.reason if exc.response is not None else exc
        print(f"error: HTTP {status} for {args.url}: {reason}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"error: failed to fetch {args.url}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if result == "created":
        log(f"Wrote new file     : {dest}")
    elif result == "updated":
        log(f"Overwrote file     : {dest}\n(SHA-256 differed)")
    else:
        log(f"Left file intact   : {dest}\n(SHA-256 matched; download discarded)")

    write_github_output(changed=result in {"created", "updated"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

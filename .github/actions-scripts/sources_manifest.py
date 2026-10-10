"""Read and validate ``sources.json``, and fill in version placeholders in URLs.

The manifest is one JSON object whose keys are the names of the sources. Each source has
the same set of keys; a key without a value is written as ``""``, ``[]``, ``0`` or ``false``:

    is-in-use         false means every tool ignores the entry
    download          false means this script does not fetch the entry (``psf_font_maker``
                      still reads it): a source that is kept in the repository by hand, or
                      that the font build fetches itself when needed
    version           required only if the URL uses a {placeholder}
    url               may contain {version} {major} {minor} {patch} {major_minor}
    sha256            SHA-256 of the archive as last installed. A download with this SHA-256
                      is the same file, so there is nothing to do; any other means the
                      archive changed, and its files are compared with what is installed
    filename          what to call the downloaded file; default: the last segment of the URL
    user-agent        overrides the default manifest-mode User-Agent
    destination-path  directory (relative to the repository root) the files are put in
    archive           how the archive is unpacked:
        strip-components  leading path parts removed from archive members (like tar's)
        keep-archive      also keep the downloaded archive in the destination
    matched-fonts     globs; only matching files are kept (all files if empty)
    keep-files        files in the destination that belong to this project (its own
                      LICENSE.md and so on); they survive every update of the tree
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field
from itertools import starmap
from pathlib import Path

_SOURCE_KEYS = {
    "is-in-use",
    "download",
    "version",
    "url",
    "sha256",
    "filename",
    "user-agent",
    "destination-path",
    "archive",
    "matched-fonts",
    "keep-files",
}
_ARCHIVE_KEYS = {"strip-components", "keep-archive"}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceError(Exception):
    """A manifest entry is invalid or its archive cannot be used."""


@dataclass(frozen=True)
class FetchOptions:
    """How an archive is requested."""

    filename: str | None = None
    user_agent: str | None = None
    download: bool = True
    sha256: str | None = None


@dataclass(frozen=True)
class UnpackOptions:
    """How an archive is unpacked."""

    strip_components: int = 0
    include: tuple[str, ...] = ()
    keep: tuple[str, ...] = ()
    keep_archive: bool = False


@dataclass(frozen=True)
class Source:
    """One entry of the sources manifest."""

    name: str
    url: str
    dest: str
    version: str | None = None
    enabled: bool = True
    fetch: FetchOptions = field(default_factory=FetchOptions)
    unpack: UnpackOptions = field(default_factory=UnpackOptions)


def _optional_text(entry: dict, key: str, label: str) -> str | None:
    """Return an optional string field of *entry*, checking its type."""
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        message = f"{label}: '{key}' must be a string (\"\" for none)"
        raise SourceError(message)
    return value.strip() or None


def _required_text(entry: dict, key: str, label: str) -> str:
    """Return a mandatory string field of *entry*, checking its type."""
    value = _optional_text(entry, key, label)
    if value is None:
        message = f"{label}: '{key}' is required and must be a string"
        raise SourceError(message)
    return value


def _flag(entry: dict, key: str, label: str, *, default: bool) -> bool:
    """Return a boolean field of *entry*, checking its type."""
    value = entry.get(key, default)
    if not isinstance(value, bool):
        message = f"{label}: '{key}' must be true or false"
        raise SourceError(message)
    return value


def _strip_count(archive: dict, label: str) -> int:
    """Return ``strip-components`` of *archive*, checking it is a non-negative integer."""
    value = archive.get("strip-components", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        message = f"{label}: 'strip-components' must be an integer >= 0"
        raise SourceError(message)
    return value


def _strings(entry: dict, label: str, key: str) -> tuple[str, ...]:
    """Return the list of non-empty strings under *key* of *entry*."""
    values = entry.get(key, [])
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        message = f"{label}: '{key}' must be a list of non-empty strings"
        raise SourceError(message)
    return tuple(values)


def _kept(entry: dict, label: str) -> tuple[str, ...]:
    """Return the ``keep-files`` of *entry*, each a relative path inside the destination."""
    names = _strings(entry, label, "keep-files")
    for name in names:
        clean = posixpath.normpath(name.replace("\\", "/"))
        if clean.startswith(("/", "..")) or _DRIVE_RE.match(clean) or clean != name:
            message = f"{label}: 'keep-files' entries must be plain relative paths, not {name!r}"
            raise SourceError(message)
    return names


def _destination(raw: str, label: str) -> str:
    """Normalise *raw* and require it to be a relative path inside the repository."""
    dest = posixpath.normpath(raw.replace("\\", "/"))
    if dest in {".", ""} or dest.startswith(("/", "..")) or _DRIVE_RE.match(dest):
        message = f"{label}: 'destination-path' must be a relative path inside the repository"
        raise SourceError(message)
    return dest


def _checksum(entry: dict, label: str) -> str | None:
    """Return the optional ``sha256`` of *entry* in lower case, checking its form."""
    value = _optional_text(entry, "sha256", label)
    if value is None:
        return None
    if not _SHA256_RE.match(value.lower()):
        message = f"{label}: 'sha256' must be 64 hexadecimal digits"
        raise SourceError(message)
    return value.lower()


def _archive_settings(entry: dict, label: str) -> dict:
    """Return the ``archive`` object of *entry*, checking its keys."""
    archive = entry.get("archive", {})
    if not isinstance(archive, dict):
        message = f"{label}: 'archive' must be an object"
        raise SourceError(message)
    unknown = set(archive) - _ARCHIVE_KEYS
    if unknown:
        message = f"{label}: unknown keys in 'archive' {sorted(unknown)}"
        raise SourceError(message)
    return archive


def _parse_entry(name: str, entry: object) -> Source:
    """Validate the manifest entry called *name* and return it as a :class:`Source`."""
    label = f"entry {name!r}"
    if not isinstance(entry, dict):
        message = f"{label}: must be an object"
        raise SourceError(message)
    unknown = set(entry) - _SOURCE_KEYS
    if unknown:
        message = f"{label}: unknown keys {sorted(unknown)}"
        raise SourceError(message)
    if not _NAME_RE.match(name):
        message = f"{label}: name may only use letters, digits, '.', '_' and '-'"
        raise SourceError(message)

    download = _flag(entry, "download", label, default=True)
    url = _required_text(entry, "url", label) if download else _optional_text(entry, "url", label)
    destination = _required_text(entry, "destination-path", label)
    archive = _archive_settings(entry, label)
    return Source(
        name=name,
        url=url or "",
        dest=_destination(destination, label),
        version=_optional_text(entry, "version", label),
        enabled=_flag(entry, "is-in-use", label, default=True),
        fetch=FetchOptions(
            filename=_optional_text(entry, "filename", label),
            user_agent=_optional_text(entry, "user-agent", label),
            download=download,
            sha256=_checksum(entry, label),
        ),
        unpack=UnpackOptions(
            strip_components=_strip_count(archive, label),
            include=_strings(entry, label, "matched-fonts"),
            keep=_kept(entry, label),
            keep_archive=_flag(archive, "keep-archive", label, default=False),
        ),
    )


def _check_unique(sources: list[Source]) -> None:
    """Reject destinations that are the same as or inside another."""
    for first in sources:
        for second in sources:
            if first is not second and (
                first.dest == second.dest or second.dest.startswith(first.dest + "/")
            ):
                message = (
                    f"'destination-path' of {second.name!r} is the same as or inside that of "
                    f"{first.name!r}"
                )
                raise SourceError(message)


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    """Build a JSON object, refusing a key that appears twice (json would keep the last)."""
    result: dict = {}
    for key, value in pairs:
        if key in result:
            message = f"manifest has the key {key!r} twice"
            raise SourceError(message)
        result[key] = value
    return result


def load_sources(path: Path) -> list[Source]:
    """Read and validate the manifest at *path*."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates)
    except OSError as exc:
        message = f"cannot read manifest {path}: {exc}"
        raise SourceError(message) from exc
    except json.JSONDecodeError as exc:
        message = f"manifest {path} is not valid JSON: {exc}"
        raise SourceError(message) from exc

    if not isinstance(data, dict) or not data:
        message = "manifest must be a non-empty object whose keys are the source names"
        raise SourceError(message)

    sources = list(starmap(_parse_entry, data.items()))
    _check_unique(sources)
    return sources


def update_hashes(path: Path, digests: dict[str, str]) -> None:
    """Write the new ``sha256`` of the sources in *digests* into the manifest at *path*."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for name, digest in digests.items():
        data[name]["sha256"] = digest
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
        message = f"{label}: uses a {{placeholder}} but has no 'version'"
        raise SourceError(message)
    fields = version_fields(version)

    def replace(match: re.Match[str]) -> str:
        """Return the value for one ``{key}`` placeholder."""
        key = match.group(1)
        if key not in fields:
            message = f"{label}: placeholder {{{key}}} is not available for version {version!r}"
            raise SourceError(message)
        return fields[key]

    return _PLACEHOLDER_RE.sub(replace, template)


def resolve_dest(root: Path, dest: str) -> Path:
    """Return the absolute *dest* below *root*, refusing anything that escapes."""
    root = root.resolve()
    path = (root / dest).resolve()
    if path == root or root not in path.parents:
        message = f"destination {dest!r} is outside the repository"
        raise SourceError(message)
    return path

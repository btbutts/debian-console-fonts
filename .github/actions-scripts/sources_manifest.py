"""Read and validate ``sources.json``, and fill in version placeholders in URLs.

Each manifest entry names an archive to download (``url``), where to unpack it
(``dest``, relative to the repository root) and how:

    name              unique name, also the key in the lock file
    url               may contain {version} {major} {minor} {patch} {major_minor}
    dest              directory the archive is unpacked into
    version           optional; required only if the URL uses a placeholder
    filename          optional; defaults to the last segment of the URL
    strip_components  optional, leading path parts removed from archive members
    include           optional list of globs; only matching files are kept
    enabled           optional, default true; false entries are ignored
    keep_archive      optional, default false; also keep the downloaded archive
    user_agent        optional; overrides the default manifest-mode User-Agent
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

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
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class SourceError(Exception):
    """A manifest entry is invalid or its archive cannot be used."""


@dataclass(frozen=True)
class FetchOptions:
    """How an archive is requested."""

    filename: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True)
class UnpackOptions:
    """How an archive is unpacked."""

    strip_components: int = 0
    include: tuple[str, ...] = ()
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
    if not isinstance(value, str) or not value.strip():
        message = f"{label}: '{key}' must be a non-empty string"
        raise SourceError(message)
    return value.strip()


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


def _strip_count(entry: dict, label: str) -> int:
    """Return ``strip_components`` of *entry*, checking it is a non-negative integer."""
    value = entry.get("strip_components", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        message = f"{label}: 'strip_components' must be an integer >= 0"
        raise SourceError(message)
    return value


def _globs(entry: dict, label: str) -> tuple[str, ...]:
    """Return the ``include`` globs of *entry*."""
    include = entry.get("include", [])
    if not isinstance(include, list) or not all(isinstance(g, str) and g for g in include):
        message = f"{label}: 'include' must be a list of non-empty strings"
        raise SourceError(message)
    return tuple(include)


def _destination(raw: str, label: str) -> str:
    """Normalise *raw* and require it to be a relative path inside the repository."""
    dest = posixpath.normpath(raw.replace("\\", "/"))
    if dest in {".", ""} or dest.startswith(("/", "..")) or _DRIVE_RE.match(dest):
        message = f"{label}: 'dest' must be a relative path inside the repository"
        raise SourceError(message)
    return dest


def _parse_entry(entry: object, index: int) -> Source:
    """Validate one manifest entry and return it as a :class:`Source`."""
    label = f"entry {index + 1}"
    if not isinstance(entry, dict):
        message = f"{label}: must be an object"
        raise SourceError(message)
    label = f"entry {entry.get('name', index + 1)!r}"
    unknown = set(entry) - _SOURCE_KEYS
    if unknown:
        message = f"{label}: unknown keys {sorted(unknown)}"
        raise SourceError(message)

    name = _required_text(entry, "name", label)
    url = _required_text(entry, "url", label)
    dest = _required_text(entry, "dest", label)
    if not _NAME_RE.match(name):
        message = f"{label}: name may only use letters, digits, '.', '_' and '-'"
        raise SourceError(message)

    return Source(
        name=name,
        url=url,
        dest=_destination(dest, label),
        version=_optional_text(entry, "version", label),
        enabled=_flag(entry, "enabled", label, default=True),
        fetch=FetchOptions(
            filename=_optional_text(entry, "filename", label),
            user_agent=_optional_text(entry, "user_agent", label),
        ),
        unpack=UnpackOptions(
            strip_components=_strip_count(entry, label),
            include=_globs(entry, label),
            keep_archive=_flag(entry, "keep_archive", label, default=False),
        ),
    )


def _check_unique(sources: list[Source]) -> None:
    """Reject duplicate names and destinations that are the same as or inside another."""
    names = [source.name for source in sources]
    if len(set(names)) != len(names):
        message = "manifest has duplicate names"
        raise SourceError(message)
    for first in sources:
        for second in sources:
            if first is not second and (
                first.dest == second.dest or second.dest.startswith(first.dest + "/")
            ):
                message = (
                    f"'dest' of {second.name!r} is the same as or inside that of {first.name!r}"
                )
                raise SourceError(message)


def load_sources(path: Path) -> list[Source]:
    """Read and validate the manifest at *path*."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        message = f"cannot read manifest {path}: {exc}"
        raise SourceError(message) from exc
    except json.JSONDecodeError as exc:
        message = f"manifest {path} is not valid JSON: {exc}"
        raise SourceError(message) from exc

    entries = data.get("sources") if isinstance(data, dict) else data
    if not isinstance(entries, list) or not entries:
        message = 'manifest must be a non-empty list (or {"sources": [...]})'
        raise SourceError(message)

    sources = [_parse_entry(entry, index) for index, entry in enumerate(entries)]
    _check_unique(sources)
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

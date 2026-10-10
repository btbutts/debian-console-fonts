"""Read ``sources.json``: where each source lives, and where to fetch those fetched on demand.

The manifest is shared with the dependency downloader, which keeps the fonts up to date.
This tool uses the ``destination-path`` of an entry as the directory its files are in,
resolved against the directory the manifest is in, so the paths are written down in one place
only. The manifest is an object whose keys are the source names.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from psf_font_maker.common.errors import ToolError

PLACEHOLDER = re.compile(r"\{(\w+)\}")
VERSION = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


class ManifestError(ToolError):
    """``sources.json`` is missing, unreadable or lacks what the tool needs."""


@dataclass(frozen=True)
class SourceEntry:
    """One source of the manifest, with its paths made absolute."""

    name: str
    directory: Path
    url: str
    version: str
    sha256: str


def version_fields(version: str) -> dict[str, str]:
    """Return the placeholder values derived from *version*."""
    fields = {"version": version}
    match = VERSION.match(version)
    if match:
        major, minor, patch = match.groups()
        fields["major"] = major
        if minor is not None:
            fields.update(minor=minor, major_minor=f"{major}.{minor}")
        if patch is not None:
            fields["patch"] = patch
    return fields


def expand_url(template: str, version: str, name: str) -> str:
    """Fill the ``{version}``-style placeholders of *template*."""
    fields = version_fields(version)

    def replace(match: re.Match[str]) -> str:
        """Return the value for one placeholder."""
        key = match.group(1)
        if key not in fields:
            message = f"source {name!r}: placeholder {{{key}}} has no value for {version!r}"
            raise ManifestError(message)
        return fields[key]

    return PLACEHOLDER.sub(replace, template)


class Manifest:
    """The sources of ``sources.json``, looked up by name."""

    def __init__(self, path: Path) -> None:
        """Read the manifest at *path*; paths in it are relative to its directory."""
        self.path = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            message = f"cannot read the sources manifest {path}: {exc}"
            raise ManifestError(message) from exc
        if not isinstance(data, dict):
            message = f"{path}: expected an object whose keys are the source names"
            raise ManifestError(message)
        self._entries = {
            name: entry for name, entry in data.items() if isinstance(entry, dict)
        }

    def names(self) -> list[str]:
        """Return the names of the sources, in the order of the manifest."""
        return list(self._entries)

    def entry(self, name: str) -> SourceEntry:
        """Return source *name*; it is an error if the manifest does not list it."""
        raw = self._entries.get(name)
        if raw is None or not raw.get("destination-path"):
            message = f"{self.path} has no source {name!r} with a 'destination-path'"
            raise ManifestError(message)
        if raw.get("is-in-use") is False:
            message = f"source {name!r} is marked \"is-in-use\": false in {self.path}"
            raise ManifestError(message)
        version = str(raw.get("version") or "")
        url = str(raw.get("url") or "")
        return SourceEntry(
            name=name,
            directory=self.path.resolve().parent / raw["destination-path"],
            url=expand_url(url, version, name) if url else "",
            version=version,
            sha256=str(raw.get("sha256") or ""),
        )

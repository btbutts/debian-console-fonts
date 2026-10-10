"""Find a FreeType library that is new enough, in the places one is likely to be."""

from __future__ import annotations

import ctypes.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from psf_font_maker.freetype_lib.errors import FreetypeError
from psf_font_maker.otf2bdf.library import library_files, probe_version
from psf_font_maker.otf2bdf.render import MINIMUM_FREETYPE

Version = tuple[int, int, int]

LIBRARY_PATH_VARIABLES = ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH")
SYSTEM_DIRS = (
    "/usr/local/lib",
    "/usr/lib",
    "/usr/lib64",
    "/lib",
    "/lib64",
    "/opt/homebrew/lib",
    "/opt/local/lib",
)
MULTIARCH_PARENTS = ("/usr/lib", "/lib")
MULTIARCH_PATTERN = "*-linux-*"
LIBRARY_DIRS = ("lib", "lib64")


@dataclass(frozen=True)
class Located:
    """A usable FreeType: the directory it is in, or None if the default loader finds it."""

    directory: Path | None
    version: Version


def text(version: Version) -> str:
    """Return *version* as dotted text."""
    return ".".join(str(part) for part in version)


def host_dirs() -> list[Path]:
    """Return the directories of a Buildroot host tree: its ``HOST_DIR`` and Python's prefix."""
    roots = [os.environ.get("HOST_DIR"), sys.prefix, sys.base_prefix]
    return [Path(root) / name for root in roots if root for name in LIBRARY_DIRS]


def system_dirs() -> list[Path]:
    """Return the directories the system keeps libraries in, on Linux and macOS."""
    from_environment = [
        Path(part)
        for variable in LIBRARY_PATH_VARIABLES
        for part in os.environ.get(variable, "").split(os.pathsep)
        if part
    ]
    multiarch = [
        path
        for parent in MULTIARCH_PARENTS
        for path in sorted(Path(parent).glob(MULTIARCH_PATTERN))
        if path.is_dir()
    ]
    return [*from_environment, *multiarch, *(Path(name) for name in SYSTEM_DIRS)]


def search(directories: list[Path], rejected: list[str]) -> Located | None:
    """Return the first FreeType in *directories* that is new enough.

    Libraries that are found but too old or unusable are described in *rejected*.
    """
    seen: set[Path] = set()
    for directory in directories:
        if directory in seen or not directory.is_dir():
            continue
        seen.add(directory)
        for library in library_files(directory):
            version = probe_version(library)
            if version is None:
                rejected.append(f"{library}: not a usable FreeType library")
            elif version < MINIMUM_FREETYPE:
                rejected.append(f"{library}: FreeType {text(version)}")
            else:
                return Located(directory, version)
    return None


def by_name(rejected: list[str]) -> Located | None:
    """Return the FreeType that the system's loader finds by name, if it is new enough."""
    name = ctypes.util.find_library("freetype")
    version = probe_version(name) if name else None
    if name and version is not None:
        if version >= MINIMUM_FREETYPE:
            return Located(None, version)
        rejected.append(f"{name}: FreeType {text(version)}")
    return None


def explicit(directories: list[Path]) -> Located:
    """Return the FreeType in the directories the user named; it is an error if none is."""
    rejected: list[str] = []
    found = search(directories, rejected)
    if found is None:
        wanted = text(MINIMUM_FREETYPE)
        detail = "; ".join(rejected) or "no libfreetype in " + ", ".join(map(str, directories))
        message = f"the FreeType you named is not usable (need {wanted} or later): {detail}"
        raise FreetypeError(message)
    return found


def locate(built: Path) -> tuple[Located | None, list[str]]:
    """Look for a usable FreeType; return it (or None) and what was found but rejected.

    The places, in order: a copy built earlier in *built*, a Buildroot host tree, the system.
    """
    rejected: list[str] = []
    found = search([built], rejected) or search(host_dirs(), rejected)
    found = found or search(system_dirs(), rejected) or by_name(rejected)
    return found, rejected

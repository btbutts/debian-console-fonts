"""Find a FreeType library that is new enough, in the places one is likely to be."""

from __future__ import annotations

import ctypes.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from psf_font_maker.common.log import detail
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

    Each directory looked at is written on the log. Libraries that are found but too old or
    unusable are described in *rejected*.
    """
    wanted = text(MINIMUM_FREETYPE)
    seen: set[Path] = set()
    for directory in directories:
        if directory in seen:
            continue
        seen.add(directory)
        if not directory.is_dir():
            detail(f"{directory}: no such directory", 2)
            continue
        libraries = library_files(directory)
        if not libraries:
            detail(f"{directory}: no libfreetype", 2)
        for library in libraries:
            version = probe_version(library)
            if version is None:
                rejected.append(f"{library}: not a usable FreeType library")
                detail(f"{library}: not a usable FreeType library", 2)
            elif version < MINIMUM_FREETYPE:
                rejected.append(f"{library}: FreeType {text(version)}")
                detail(f"{library}: FreeType {text(version)}, too old (need {wanted})", 2)
            else:
                detail(f"{library}: FreeType {text(version)}, new enough (need {wanted})", 2)
                return Located(directory, version)
    return None


def by_name(rejected: list[str]) -> Located | None:
    """Return the FreeType that the system's loader finds by name, if it is new enough."""
    name = ctypes.util.find_library("freetype")
    if not name:
        detail("the system's loader (ctypes.util.find_library): no FreeType", 2)
        return None
    version = probe_version(name)
    if version is None:
        detail(f"the system's loader gave {name}, which is not a usable FreeType library", 2)
        return None
    if version >= MINIMUM_FREETYPE:
        detail(f"the system's loader gave {name}: FreeType {text(version)}, new enough", 2)
        return Located(None, version)
    rejected.append(f"{name}: FreeType {text(version)}")
    detail(f"the system's loader gave {name}: FreeType {text(version)}, too old", 2)
    return None


def explicit(directories: list[Path]) -> Located:
    """Return the FreeType in the directories the user named; it is an error if none is."""
    rejected: list[str] = []
    detail("looking only in the directory you named:")
    found = search(directories, rejected)
    if found is None:
        wanted = text(MINIMUM_FREETYPE)
        reason = "; ".join(rejected) or "no libfreetype in " + ", ".join(map(str, directories))
        message = f"the FreeType you named is not usable (need {wanted} or later): {reason}"
        raise FreetypeError(message)
    return found


def locate(built: Path) -> tuple[Located | None, list[str]]:
    """Look for a usable FreeType; return it (or None) and what was found but rejected.

    The places, in order: a copy built earlier in *built*, a Buildroot host tree, the system.
    """
    rejected: list[str] = []
    detail(f"looking for a FreeType {text(MINIMUM_FREETYPE)} or later:")
    detail("a copy built earlier by this tool:")
    found = search([built], rejected)
    if found is None:
        detail("a Buildroot host tree (HOST_DIR) or this Python's prefix:")
        found = search(host_dirs(), rejected)
    if found is None:
        detail("the system's library directories:")
        found = search(system_dirs(), rejected) or by_name(rejected)
    return found, rejected

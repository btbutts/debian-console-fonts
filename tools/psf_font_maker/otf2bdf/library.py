"""Find a FreeType shared library and read its version without the freetype-py package."""

from __future__ import annotations

import ctypes
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Names the environment variable that points freetype-py at a directory holding libfreetype.
LIBRARY_DIR_ENV = "PSF_FONT_MAKER_FREETYPE_DIR"
PATTERNS = {
    "darwin": ("libfreetype*.dylib",),
    "win32": ("libfreetype*.dll", "freetype*.dll"),
}
DEFAULT_PATTERNS = ("libfreetype.so*",)


def library_files(directory: Path) -> list[Path]:
    """Return the FreeType shared libraries in *directory*, the plainest name first."""
    patterns = PATTERNS.get(sys.platform, DEFAULT_PATTERNS)
    found = {path for pattern in patterns for path in directory.glob(pattern) if path.is_file()}
    return sorted(found, key=lambda path: (len(path.name), path.name))


def probe_version(library: Path | str) -> tuple[int, int, int] | None:
    """Return the (major, minor, patch) version of the FreeType *library*, or None.

    None means the library could not be loaded or is not FreeType.
    """
    try:
        lib = ctypes.CDLL(str(library))
        init, version, done = lib.FT_Init_FreeType, lib.FT_Library_Version, lib.FT_Done_FreeType
    except (OSError, AttributeError):
        return None
    handle = ctypes.c_void_p()
    if init(ctypes.byref(handle)) != 0:
        return None
    major, minor, patch = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
    version(handle, ctypes.byref(major), ctypes.byref(minor), ctypes.byref(patch))
    done(handle)
    return (major.value, minor.value, patch.value)

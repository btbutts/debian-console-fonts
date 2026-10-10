"""Compare PSF fonts glyph by glyph, keyed by Unicode code point."""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING

from psf_font_maker.common.psf_read import load_psf

if TYPE_CHECKING:
    from pathlib import Path

SUFFIXES = (".psf.gz", ".psf")


def compare(path_a: Path, path_b: Path) -> tuple[int, int, int, int]:
    """Return (shared code points, identical glyphs, only in A, only in B)."""
    glyphs_a = load_psf(path_a)[2]
    glyphs_b = load_psf(path_b)[2]
    shared = set(glyphs_a) & set(glyphs_b)
    same = sum(1 for code in shared if glyphs_a[code] == glyphs_b[code])
    return len(shared), same, len(set(glyphs_a) - set(glyphs_b)), len(set(glyphs_b) - set(glyphs_a))


def font_name(path: Path) -> str | None:
    """Return the font name (file name without .psf/.psf.gz), or None for other files."""
    for suffix in SUFFIXES:
        if path.name.endswith(suffix):
            return path.name[: -len(suffix)]
    return None


def font_files(directory: Path, pattern: str) -> dict[str, Path]:
    """Return {font name: path} for the fonts in *directory* matching *pattern*."""
    found = {}
    for path in sorted(directory.iterdir()):
        name = font_name(path)
        if name is not None and fnmatch.fnmatch(name, pattern):
            found[name] = path
    return found


def percent(part: int, whole: int) -> float:
    """Return *part* as a percentage of *whole*; an empty whole counts as 100%."""
    return 100.0 * part / whole if whole else 100.0

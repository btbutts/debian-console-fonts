"""Helpers shared by several test modules."""

from __future__ import annotations

import pytest

from psf_font_maker.otf2bdf import render
from psf_font_maker.otf2bdf.errors import RenderError


def freetype_usable() -> bool:
    """Return True if freetype-py is installed with a FreeType new enough to render."""
    try:
        render.load_freetype()
    except RenderError:
        return False
    return True


needs_freetype = pytest.mark.skipif(
    not freetype_usable(), reason="rendering TrueType fonts needs a recent enough FreeType"
)

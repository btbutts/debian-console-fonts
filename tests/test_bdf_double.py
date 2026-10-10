"""Tests for the bdf-double tool of psf_font_maker."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from psf_font_maker.bdf_double import enlarge as bdf_double

ROOT = Path(__file__).resolve().parents[1]
UNI_VGA = ROOT / "sources" / "uni-vga" / "u_vga16.bdf"
DEBIAN_DOUBLE = ROOT / "sources" / "console-setup" / "Fonts" / "bdf" / "u_vga16-double.bdf"

TINY_FONT = """STARTFONT 2.1
FONT tiny
SIZE 3 75 75
FONTBOUNDINGBOX 3 2 0 -1
STARTPROPERTIES 3
FONT_DESCENT 1
FONT_ASCENT 1
DEFAULT_CHAR 0
ENDPROPERTIES
CHARS 1
STARTCHAR u0041
ENCODING 65
SWIDTH 500 0
DWIDTH 3 0
BBX 3 2 0 -1
BITMAP
A0
40
ENDCHAR
ENDFONT
"""


def glyph_table(text: str) -> dict[int, tuple[str, tuple[str, ...]]]:
    """Return {encoding: (BBX line, bitmap rows)} for every glyph in BDF *text*."""
    table = {}
    for block in re.findall(r"STARTCHAR.*?ENDCHAR", text, re.DOTALL):
        lines = block.splitlines()
        encoding = int(next(line for line in lines if line.startswith("ENCODING")).split()[1])
        bbx = next(line for line in lines if line.startswith("BBX"))
        rows = tuple(lines[lines.index("BITMAP") + 1 : -1])
        table[encoding] = (bbx, tuple(row.upper() for row in rows))
    return table


def test_every_pixel_becomes_a_two_by_two_block() -> None:
    """0b101 over 0b010 becomes six columns and four rows."""
    out = bdf_double.convert(TINY_FONT, "tiny.bdf")
    assert "FONTBOUNDINGBOX 6 4 0 -2" in out
    assert "SIZE 6 75 75" in out
    assert "FONT_ASCENT 2" in out
    assert "DEFAULT_CHAR 0" in out
    assert glyph_table(out)[65] == ("BBX 6 4 0 -2", ("CC", "CC", "30", "30"))


def test_glyph_metrics_are_doubled() -> None:
    """The advance width doubles; the scalable width is doubled too."""
    out = bdf_double.convert(TINY_FONT, "tiny.bdf")
    assert "DWIDTH 6 0" in out
    assert "SWIDTH 1000 0" in out


def test_input_without_glyphs_is_rejected() -> None:
    """A file with no characters is an error, not an empty font."""
    with pytest.raises(bdf_double.BdfError):
        bdf_double.convert("STARTFONT 2.1\nENDFONT\n", "empty.bdf")


@pytest.mark.skipif(
    not (UNI_VGA.is_file() and DEBIAN_DOUBLE.is_file()), reason="sources/ not populated"
)
def test_enlarging_uni_vga_matches_console_setups_double() -> None:
    """Our enlargement of Uni-VGA has the same glyphs as console-setup's bdfresize output."""
    ours = glyph_table(bdf_double.convert(UNI_VGA.read_text(encoding="latin-1"), UNI_VGA.name))
    theirs = glyph_table(DEBIAN_DOUBLE.read_text(encoding="latin-1"))
    assert ours == theirs

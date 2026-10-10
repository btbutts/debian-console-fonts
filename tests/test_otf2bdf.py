"""Tests for the otf2bdf renderer of psf_font_maker."""

from __future__ import annotations

import importlib
import types
from pathlib import Path

import pytest
from support import needs_freetype

from psf_font_maker.bdf2psf.bdf_reader import GlyphSet, read_bdf
from psf_font_maker.main import main
from psf_font_maker.otf2bdf import render
from psf_font_maker.otf2bdf.bdf_text import to_bdf
from psf_font_maker.otf2bdf.crop import crop_bitmap
from psf_font_maker.otf2bdf.errors import RenderError
from psf_font_maker.otf2bdf.glyphs import Size
from psf_font_maker.otf2bdf.render import as_short, render_font, trunc_div
from psf_font_maker.otf2bdf.tables import read_hhea

ROOT = Path(__file__).resolve().parents[1]
MONO = ROOT / "data" / "fontsets" / "dejavu" / "ttf" / "DejaVuSansMono.ttf"


needs_font = pytest.mark.skipif(not MONO.is_file(), reason="DejaVu not downloaded")

CELL_WIDTH = 16
CELL_HEIGHT = 30
LETTER_A = 0x41
MIN_GLYPHS = 3000
WRAPPED = 40000
SHORT_RANGE = 65536
SMALL_NEGATIVE = -5
QUOTIENT = 3
ASCENDER = 1901
DESCENDER = -483
PITCH = 2
BITMAP_WIDTH = 12
BITMAP_ROWS = 4
WIDE_ROW = 10


# --------------------------------------------------------------------------
# pieces that need no FreeType
# --------------------------------------------------------------------------


def test_crop_keeps_only_the_set_pixels() -> None:
    """A 12x4 bitmap with ink in columns 2-5 of rows 1-2 crops to a 4x2 box."""
    rows = [0b0000_0000_0000_0000, 0b0011_1100_0000_0000, 0b0010_0100_0000_0000, 0]
    buffer = b"".join(row.to_bytes(PITCH, "big") for row in rows)
    crop = crop_bitmap(buffer, BITMAP_WIDTH, BITMAP_ROWS, PITCH)
    assert (crop.left, crop.right, crop.top, crop.bottom) == (2, 6, 1, 3)
    assert (crop.width, crop.height) == (4, 2)
    assert crop.rows == ["F0", "90"]


def test_crop_ignores_padding_bits() -> None:
    """Bits beyond the bitmap width are padding, not ink."""
    crop = crop_bitmap(b"\x00\x0f", 8, 1, PITCH)
    assert not crop.rows
    assert crop.width == crop.height == 0


def test_crop_pads_wide_rows_to_whole_bytes() -> None:
    """A row 10 pixels wide is written as two bytes, padded with zeros on the right."""
    crop = crop_bitmap((0b1000_0000_0100_0000).to_bytes(PITCH, "big"), 16, 1, PITCH)
    assert crop.width == WIDE_ROW
    assert crop.rows == ["8040"]


def test_division_rounds_towards_zero_like_c() -> None:
    """Ascent and descent are computed with C integer division."""
    assert trunc_div(QUOTIENT * 2 + 1, 2) == QUOTIENT
    assert trunc_div(-(QUOTIENT * 2 + 1), 2) == -QUOTIENT


def test_short_arithmetic_wraps() -> None:
    """SWIDTH is stored in a 16-bit signed field."""
    assert as_short(WRAPPED) == WRAPPED - SHORT_RANGE
    assert as_short(SMALL_NEGATIVE) == SMALL_NEGATIVE


@needs_font
def test_hhea_values_are_read_from_the_font_file() -> None:
    """DejaVu Sans Mono's ascender and descender, in font units."""
    assert read_hhea(MONO) == (ASCENDER, DESCENDER)


def test_old_freetype_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A FreeType older than the minimum is an error that says how to get a newer one."""
    fake = types.SimpleNamespace(version=lambda: (2, 13, 2))
    monkeypatch.setattr(importlib, "import_module", lambda _: fake)
    with pytest.raises(RenderError, match=r"too old.*--no-binary"):
        render.load_freetype()
    fake.version = lambda: render.MINIMUM_FREETYPE
    assert render.load_freetype() is fake


def test_missing_freetype_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without freetype-py the error says what to install."""

    def refuse(name: str) -> None:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", refuse)
    with pytest.raises(RenderError, match="pip install freetype-py"):
        render.load_freetype()


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


@needs_freetype
@needs_font
def test_dejavu_renders_to_a_cell_of_the_expected_size() -> None:
    """DejaVu Sans Mono at 16 points and 115 dpi has a 30 pixel high cell."""
    font = render_font(MONO, Size(CELL_WIDTH, 115))
    assert font.vertical.ascent + font.vertical.descent == CELL_HEIGHT
    assert font.info.family == "DejaVu Sans Mono"
    assert not font.info.bold
    assert len(font.glyphs) > MIN_GLYPHS
    assert any(glyph.code == LETTER_A and glyph.rows for glyph in font.glyphs)


@needs_freetype
@needs_font
def test_bdf_text_reads_back_as_a_full_cell(tmp_path: Path) -> None:
    """The BDF is accepted by the reader bdf2psf uses, with the cell width we asked for."""
    font = render_font(MONO, Size(CELL_WIDTH, 115))
    bdf = tmp_path / "dejavu.bdf"
    bdf.write_text(to_bdf(font, "C", CELL_WIDTH), encoding="latin-1")
    glyph_set = GlyphSet()
    read_bdf(bdf, glyph_set, lambda _: None)
    assert (glyph_set.width, glyph_set.height) == (CELL_WIDTH, CELL_HEIGHT)
    assert len(glyph_set.glyphs[LETTER_A]) == glyph_set.matrix_size
    assert any(glyph_set.glyphs[LETTER_A])


@needs_freetype
@needs_font
def test_command_line_prints_height_and_writes_a_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--height`` prints the cell height; ``-o`` writes the font."""
    assert main(["otf2bdf", "--height", "-p", "16", "-r", "115", str(MONO)]) == 0
    assert capsys.readouterr().out.strip() == str(CELL_HEIGHT)
    out = tmp_path / "out.bdf"
    assert main(["otf2bdf", "-c", "C", "-p", "16", "-r", "115", "-o", str(out), str(MONO)]) == 0
    text = out.read_text(encoding="latin-1")
    assert text.startswith("STARTFONT 2.1\n")
    assert "FONT_ASCENT" in text
    assert text.endswith("ENDFONT\n")


@needs_freetype
def test_a_file_that_is_not_a_font_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """FreeType's complaint is reported as an error message, not a traceback."""
    junk = tmp_path / "junk.ttf"
    junk.write_bytes(b"not a font")
    assert main(["otf2bdf", str(junk)]) == 1
    assert "junk.ttf" in capsys.readouterr().err

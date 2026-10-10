"""Turn a finished layout into the bytes of a font, or of its symbol table."""

from __future__ import annotations

from itertools import islice
from typing import TYPE_CHECKING

from psf_font_maker.bdf2psf.classify import RAW
from psf_font_maker.bdf2psf.random48 import rand_bytes
from psf_font_maker.common import psf

if TYPE_CHECKING:
    from psf_font_maker.bdf2psf.layout import Layout


def positions_to_codes(layout: Layout) -> list[int | None]:
    """Return, for every position, the code whose glyph is drawn there."""
    glyphs = layout.glyph_set.glyphs
    chosen: list[int | None] = [None] * layout.font_size
    for position, members in enumerate(layout.classes):
        for code in members or ():
            if code in glyphs:
                chosen[position] = code
                break
    return chosen


def glyph_matrix(layout: Layout, chosen: list[int | None]) -> bytes:
    """Return the bitmaps of all positions; unused ones get Perl's pseudo-random filler."""
    filler = rand_bytes(0)
    size = layout.glyph_set.matrix_size
    out = bytearray()
    for code in chosen:
        if code is None:
            out.extend(islice(filler, size))
        else:
            glyph = layout.glyph_set.glyphs[code]
            out.extend((glyph + [0] * size)[:size])
    return bytes(out)


def encode(layout: Layout) -> bytes:
    """Return the complete font file for a finished layout."""
    body = glyph_matrix(layout, positions_to_codes(layout))
    if layout.font_type == RAW:
        return body
    glyph_set = layout.glyph_set
    return psf.assemble(glyph_set.width, glyph_set.height, body, layout.classes)


def sfm_text(layout: Layout) -> str:
    """Return the same position-to-symbols mapping as a text table."""
    lines = []
    for position in range(layout.font_size):
        symbols = "".join(f" U+{code:04x}" for code in layout.classes[position] or ())
        lines.append(f"0x{position:02x}    {symbols}\n")
    return "".join(lines)

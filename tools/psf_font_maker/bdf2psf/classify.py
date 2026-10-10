"""Decide how each glyph treats the 9th pixel column of a VGA text mode.

A text-mode VGA adapter copies the 8th pixel column into the 9th for the codes
0xC0 to 0xDF only. The glyphs are sorted by whether they need that copy, so they
can be put at suitable positions. Framebuffer fonts have no such restriction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from psf_font_maker.bdf2psf.errors import ClassifyError

if TYPE_CHECKING:
    from psf_font_maker.bdf2psf.bdf_reader import GlyphSet
    from psf_font_maker.bdf2psf.equivalence import Equivalence

COPY_8TH = 1
DONT_COPY_8TH = 2
DOESNT_MATTER_8TH = 3

FRAMEBUFFER = 0
TEXT_MODE = 1
RAW = 2

SEVEN = 7
EIGHT = 8
NINE = 9
LOW_BIT = 0x01
SECOND_BIT = 0x02
HIGH_BIT = 0x80


@dataclass
class Classification:
    """The kind of each glyph and how many pixels could not be kept as drawn."""

    types: dict[int, int] = field(default_factory=dict)
    broken_pixels: dict[int, int] = field(default_factory=dict)


def classify(glyph_set: GlyphSet, font_type: int, equivalence: Equivalence) -> Classification:
    """Classify the glyphs and, for text-mode fonts, reduce them to 8 pixels wide."""
    result = Classification()
    if font_type == FRAMEBUFFER:
        result.types = dict.fromkeys(glyph_set.glyphs, DOESNT_MATTER_8TH)
    elif font_type == RAW:
        result.types = dict.fromkeys(glyph_set.glyphs, DONT_COPY_8TH)
    elif glyph_set.width == SEVEN:
        _seven_wide(glyph_set, equivalence, result)
    elif glyph_set.width == EIGHT:
        _eight_wide(glyph_set, equivalence, result)
    elif glyph_set.width == NINE:
        _nine_wide(glyph_set, result)
    else:
        message = f"Bad symbols width for non-framebuffer font: {glyph_set.width}"
        raise ClassifyError(message)
    return result


def _seven_wide(glyph_set: GlyphSet, equivalence: Equivalence, result: Classification) -> None:
    """Widen 7-pixel glyphs to 8, duplicating the last column of box drawings."""
    for code, rows in glyph_set.glyphs.items():
        result.types[code] = DOESNT_MATTER_8TH
        if equivalence.is_box_drawings(code):
            for index in range(glyph_set.height):
                if rows[index] & SECOND_BIT:
                    rows[index] |= LOW_BIT
                    result.types[code] = COPY_8TH
    glyph_set.width = EIGHT


def _eight_wide(glyph_set: GlyphSet, equivalence: Equivalence, result: Classification) -> None:
    """Mark glyphs that use the 8th column as needing, or not needing, the copy."""
    for code, rows in glyph_set.glyphs.items():
        result.types[code] = DOESNT_MATTER_8TH
        for index in range(glyph_set.height):
            if rows[index] & LOW_BIT:
                box = equivalence.is_box_drawings(code)
                result.types[code] = COPY_8TH if box else DONT_COPY_8TH


def _nine_wide(glyph_set: GlyphSet, result: Classification) -> None:
    """Reduce 9-pixel glyphs to 8, choosing the kind that breaks the fewest pixels."""
    for code, rows in glyph_set.glyphs.items():
        pixels9 = copied = different = 0
        for index in range(glyph_set.height):
            left, right = rows[2 * index], rows[2 * index + 1]
            if (left & LOW_BIT) and not right & HIGH_BIT:
                different += 1
            if right & HIGH_BIT:
                pixels9 += 1
                if not left & LOW_BIT:
                    rows[2 * index] = left | LOW_BIT
                    copied += 1
        if different < pixels9:
            result.types[code] = COPY_8TH
            result.broken_pixels[code] = different + copied
        elif different > pixels9:
            result.types[code] = DONT_COPY_8TH
            result.broken_pixels[code] = pixels9 + copied
        else:
            result.types[code] = DOESNT_MATTER_8TH
            result.broken_pixels[code] = pixels9 + copied
        glyph_set.glyphs[code] = [rows[2 * index] for index in range(glyph_set.height)]
    glyph_set.width = EIGHT

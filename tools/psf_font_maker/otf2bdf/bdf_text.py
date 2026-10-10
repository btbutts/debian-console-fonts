"""Write a rendered font as BDF text."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psf_font_maker.otf2bdf.glyphs import RenderedFont

PIXEL_SIZE_DIVISOR = 722.7
POINT_TENTHS = 10
ROUNDING = 0.5
AVERAGE_WIDTH_TENTHS = 10


def spacing_of(font: RenderedFont, spacing: str | None) -> str:
    """Return the XLFD spacing letter: the one asked for, or M/P from the glyph widths."""
    if spacing:
        return spacing.upper()
    return "M" if font.monospaced else "P"


def pixel_size(font: RenderedFont) -> int:
    """Return the pixel size XLFD names from the point size and resolution."""
    points = font.size.point_size * POINT_TENTHS
    return int((points * font.size.resolution) / PIXEL_SIZE_DIVISOR + ROUNDING)


def xlfd_name(font: RenderedFont, spacing: str, average_width: int) -> str:
    """Return the font's XLFD name."""
    info, size = font.info, font.size
    weight = "Bold" if info.bold else "Medium"
    slant = "I" if info.italic else "R"
    return (
        f"-FreeType-{info.family.replace('-', ' ')}-{weight}-{slant}-Normal--{pixel_size(font)}"
        f"-{size.point_size * POINT_TENTHS}-{size.resolution}-{size.resolution}"
        f"-{spacing}-{average_width}-ISO10646-1"
    )


def xlfd_properties(font: RenderedFont, spacing: str, average_width: int) -> list[str]:
    """Return the properties that spell out the font's XLFD name."""
    family = font.info.family.replace("-", " ")
    quoted = {
        "FOUNDRY": "FreeType",
        "FAMILY_NAME": family,
        "WEIGHT_NAME": "Bold" if font.info.bold else "Medium",
        "SLANT": "I" if font.info.italic else "R",
        "SETWIDTH_NAME": "Normal",
        "ADD_STYLE_NAME": "",
    }
    lines = [f'{name} "{value}"' for name, value in quoted.items()]
    lines += [
        f"PIXEL_SIZE {pixel_size(font)}",
        f"POINT_SIZE {font.size.point_size * POINT_TENTHS}",
        f"RESOLUTION_X {font.size.resolution}",
        f"RESOLUTION_Y {font.size.resolution}",
        f'SPACING "{spacing}"',
        f"AVERAGE_WIDTH {average_width}",
        'CHARSET_REGISTRY "ISO10646"',
        'CHARSET_ENCODING "1"',
    ]
    return lines


def to_bdf(font: RenderedFont, spacing: str | None = None, cell_width: int | None = None) -> str:
    """Return the BDF text of *font*.

    With *cell_width* the AVERAGE_WIDTH is set to ten times it, which is how
    console-setup marks the width of the cell a font is to be converted at.
    """
    average = cell_width * AVERAGE_WIDTH_TENTHS if cell_width else font.average_width
    letter = spacing_of(font, spacing)
    box = font.box
    out = [
        "STARTFONT 2.1",
        f'COMMENT Rendered from "{font.info.file_name}" by psf_font_maker otf2bdf'
        f" with FreeType {font.info.freetype_version}.",
        f"FONT {xlfd_name(font, letter, average)}",
        f"SIZE {font.size.point_size} {font.size.resolution} {font.size.resolution}",
        f"FONTBOUNDINGBOX {box.width} {box.height} {box.min_left} {-box.max_descent}",
    ]
    properties = [
        *xlfd_properties(font, letter, average),
        f"FONT_ASCENT {font.vertical.ascent}",
        f"FONT_DESCENT {font.vertical.descent}",
        f'_OTF_FONTFILE "{font.info.file_name}"',
    ]
    out += [
        f"STARTPROPERTIES {len(properties)}",
        *properties,
        "ENDPROPERTIES",
        f"CHARS {len(font.glyphs)}",
    ]
    for glyph in font.glyphs:
        out += [
            f"STARTCHAR {glyph.code:04X}",
            f"ENCODING {glyph.code}",
            f"SWIDTH {glyph.scalable_width} 0",
            f"DWIDTH {glyph.advance} 0",
            f"BBX {glyph.box.width} {glyph.box.height} {glyph.box.x_offset} {glyph.box.y_offset}",
            "BITMAP",
            *glyph.rows,
            "ENDCHAR",
        ]
    out.append("ENDFONT")
    return "\n".join(out) + "\n"

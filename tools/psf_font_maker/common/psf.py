"""The PSF console font format (versions 1 and 2) with an embedded Unicode table."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

PSF1_MAGIC = bytes((0x36, 0x04))
PSF1_MODE_512 = 0x01
PSF1_MODE_HAS_TABLE = 0x02
PSF1_WIDTH = 8
PSF1_MAX_HEIGHT = 255
PSF2_MAGIC = bytes((0x72, 0xB5, 0x4A, 0x86))
PSF2_HEADER_SIZE = 0x20
PSF2_HAS_TABLE = 0x01
CLASSIC_SIZES = (256, 512)
SEPARATOR = 0xFF
TWO_BYTE_LIMIT = 0x7FF
ASCII_LIMIT = 0x7F


def uses_psf2(width: int, height: int, font_size: int) -> bool:
    """Return True if a font of this shape does not fit the older PSF1 format."""
    return (
        width != PSF1_WIDTH or height > PSF1_MAX_HEIGHT or font_size not in CLASSIC_SIZES
    )


def _le(value: int, size: int) -> bytes:
    """Return *value* as *size* little-endian bytes."""
    return (value & ((1 << (8 * size)) - 1)).to_bytes(size, "little")


def header(width: int, height: int, font_size: int) -> bytes:
    """Return the PSF header for a font of *font_size* glyphs of *width* by *height*."""
    if not uses_psf2(width, height, font_size):
        mode = (font_size == CLASSIC_SIZES[1]) * PSF1_MODE_512 + PSF1_MODE_HAS_TABLE
        return PSF1_MAGIC + bytes((mode, height))
    glyph_bytes = ((width + 7) >> 3) * height
    return b"".join(
        (
            PSF2_MAGIC,
            _le(0, 4),
            _le(PSF2_HEADER_SIZE, 4),
            _le(PSF2_HAS_TABLE, 4),
            _le(font_size, 4),
            _le(glyph_bytes, 4),
            _le(height, 4),
            _le(width, 4),
        )
    )


def encode_code(code: int, psf2: bool) -> bytes:
    """Return one Unicode value as it is stored in the table."""
    if not psf2:
        return _le(code, 2)
    if code <= ASCII_LIMIT:
        return bytes((code,))
    if code <= TWO_BYTE_LIMIT:
        return bytes((0xC0 + (code >> 6), 0x80 + (code & 0x3F)))
    return bytes((0xE0 + (code >> 12), 0x80 + ((code >> 6) & 0x3F), 0x80 + (code & 0x3F)))


def unicode_table(classes: Sequence[Sequence[int] | None], psf2: bool) -> bytes:
    """Return the Unicode table: each position's symbols followed by a separator."""
    out = bytearray()
    for members in classes:
        for code in members or ():
            out.extend(encode_code(code, psf2))
        out.append(SEPARATOR)
        if not psf2:
            out.append(SEPARATOR)
    return bytes(out)


def assemble(
    width: int,
    height: int,
    glyphs: bytes,
    classes: Sequence[Sequence[int] | None],
) -> bytes:
    """Return a complete PSF file from the glyph bytes and each position's symbols."""
    font_size = len(classes)
    psf2 = uses_psf2(width, height, font_size)
    return header(width, height, font_size) + glyphs + unicode_table(classes, psf2)

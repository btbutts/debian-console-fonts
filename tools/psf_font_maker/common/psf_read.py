"""Read PSF console fonts (versions 1 and 2) back into glyph bitmaps by code point."""

from __future__ import annotations

import contextlib
import gzip
import struct
from typing import TYPE_CHECKING

from psf_font_maker.common.errors import PsfFormatError
from psf_font_maker.common.psf import (
    PSF1_MAGIC,
    PSF1_MODE_512,
    PSF1_WIDTH,
    PSF2_HAS_TABLE,
    PSF2_MAGIC,
    SEPARATOR,
)

if TYPE_CHECKING:
    from pathlib import Path

GZIP_MAGIC = b"\x1f\x8b"

PSF1_HEADER_SIZE = 4
PSF1_MODE_UNICODE_TABLE = 0x06  # has-table and has-sequences bits
PSF1_SMALL_GLYPH_COUNT = 256
PSF1_LARGE_GLYPH_COUNT = 512
PSF1_END_OF_ENTRY = 0xFFFF
PSF1_START_OF_SEQUENCE = 0xFFFE

PSF2_HEADER = struct.Struct("<7I")  # version, header size, flags, length, charsize, height, width
PSF2_START_OF_SEQUENCE = 0xFE

UTF8_ONE_BYTE_END = 0x80
UTF8_TWO_BYTE_END = 0xE0
UTF8_THREE_BYTE_END = 0xF0

Glyphs = dict[int, bytes]


def read_font(path: Path) -> bytes:
    """Return the raw bytes of a font file, decompressing it if it is gzipped."""
    data = path.read_bytes()
    return gzip.decompress(data) if data[:2] == GZIP_MAGIC else data


def utf8_length(first_byte: int) -> int:
    """Return how many bytes the UTF-8 sequence starting with *first_byte* has."""
    if first_byte < UTF8_ONE_BYTE_END:
        return 1
    if first_byte < UTF8_TWO_BYTE_END:
        return 2
    return 3 if first_byte < UTF8_THREE_BYTE_END else 4


def psf1_unicode_table(raw: bytes) -> list[list[int]]:
    """Parse a PSF1 unicode table into one list of code points per glyph."""
    table: list[list[int]] = []
    current: list[int] = []
    for offset in range(0, len(raw) - 1, 2):
        value = raw[offset] | raw[offset + 1] << 8
        if value == PSF1_END_OF_ENTRY:
            table.append(current)
            current = []
        elif value != PSF1_START_OF_SEQUENCE:
            current.append(value)
    return table


def psf2_unicode_table(raw: bytes, glyph_count: int) -> list[list[int]]:
    """Parse a PSF2 unicode table into one list of code points per glyph."""
    table: list[list[int]] = []
    current: list[int] = []
    i = 0
    while i < len(raw) and len(table) < glyph_count:
        byte = raw[i]
        if byte == SEPARATOR:
            table.append(current)
            current = []
            i += 1
        elif byte == PSF2_START_OF_SEQUENCE:
            while i < len(raw) and raw[i] != SEPARATOR:  # skip combining sequences
                i += 1
        else:
            step = utf8_length(byte)
            with contextlib.suppress(UnicodeDecodeError):
                current.append(ord(raw[i : i + step].decode("utf-8")))
            i += step
    return table


def load_psf1(data: bytes) -> tuple[int, int, list[bytes], list[list[int]]]:
    """Return (width, height, glyph bitmaps, unicode table) of a PSF1 font."""
    mode, size = data[2], data[3]
    count = PSF1_LARGE_GLYPH_COUNT if mode & PSF1_MODE_512 else PSF1_SMALL_GLYPH_COUNT
    start = PSF1_HEADER_SIZE
    glyphs = [data[start + i * size : start + (i + 1) * size] for i in range(count)]
    table = []
    if mode & PSF1_MODE_UNICODE_TABLE:
        table = psf1_unicode_table(data[start + count * size :])
    return PSF1_WIDTH, size, glyphs, table


def load_psf2(data: bytes) -> tuple[int, int, list[bytes], list[list[int]]]:
    """Return (width, height, glyph bitmaps, unicode table) of a PSF2 font."""
    _, header, flags, length, size, height, width = PSF2_HEADER.unpack(
        data[len(PSF2_MAGIC) : len(PSF2_MAGIC) + PSF2_HEADER.size]
    )
    glyphs = [data[header + i * size : header + (i + 1) * size] for i in range(length)]
    table = (
        psf2_unicode_table(data[header + length * size :], length)
        if flags & PSF2_HAS_TABLE
        else []
    )
    return width, height, glyphs, table


def load_psf(path: Path) -> tuple[int, int, Glyphs]:
    """Return (width, height, {code point: bitmap}) for a PSF1 or PSF2 font."""
    data = read_font(path)
    if data[: len(PSF1_MAGIC)] == PSF1_MAGIC:
        width, height, glyphs, table = load_psf1(data)
    elif data[: len(PSF2_MAGIC)] == PSF2_MAGIC:
        width, height, glyphs, table = load_psf2(data)
    else:
        message = f"{path}: not a PSF font"
        raise PsfFormatError(message)

    by_code: Glyphs = {}
    for index, codes in enumerate(table):
        for code in codes:
            by_code.setdefault(code, glyphs[index])
    return width, height, by_code

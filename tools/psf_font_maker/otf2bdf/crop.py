"""Crop a monochrome FreeType bitmap to the pixels that are set."""

from __future__ import annotations

from dataclasses import dataclass

BITS_PER_BYTE = 8


@dataclass
class Crop:
    """The set pixels of a bitmap: their box (columns left..right, rows top..bottom)."""

    left: int
    right: int
    top: int
    bottom: int
    rows: list[str]

    @property
    def width(self) -> int:
        """The number of columns kept."""
        return self.right - self.left

    @property
    def height(self) -> int:
        """The number of rows kept."""
        return self.bottom - self.top


def crop_bitmap(buffer: bytes, width: int, rows: int, pitch: int) -> Crop:
    """Return the part of a 1-bit-per-pixel bitmap that holds set pixels.

    The rows are returned as BDF hex strings, each padded on the right to whole bytes.
    A bitmap without set pixels crops to nothing.
    """
    bits = pitch * BITS_PER_BYTE
    keep = ((1 << width) - 1) << (bits - width)
    values = [
        int.from_bytes(buffer[row * pitch : (row + 1) * pitch], "big") & keep
        for row in range(rows)
    ]
    inked = [row for row, value in enumerate(values) if value]
    if not inked:
        return Crop(0, 0, 0, 0, [])
    left = min(bits - values[row].bit_length() for row in inked)
    right = max(bits - ((values[row] & -values[row]).bit_length() - 1) for row in inked)
    top, bottom = inked[0], inked[-1] + 1
    size = right - left
    shift = bits - right
    hex_rows = [
        _hex_row((values[row] >> shift) & ((1 << size) - 1), size) for row in range(top, bottom)
    ]
    return Crop(left, right, top, bottom, hex_rows)


def _hex_row(value: int, size: int) -> str:
    """Return the *size*-bit *value* as BDF hex, padded on the right to whole bytes."""
    padded = -(-size // BITS_PER_BYTE) * BITS_PER_BYTE
    return f"{value << (padded - size):0{padded // 4}X}"

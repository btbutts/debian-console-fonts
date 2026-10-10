"""Read BDF fonts the way console-setup's bdf2psf does.

Several fonts can be merged into one :class:`GlyphSet`: the first font that defines
a code point wins. All of them must have the same height (FONT_ASCENT plus
FONT_DESCENT) and cell width (AVERAGE_WIDTH / 10).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from psf_font_maker.bdf2psf.errors import FontFormatError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

MAX_HEIGHT = 2400
MAX_WIDTH = 1200
WIDTH_DIVISOR = 10
BITS_PER_BYTE = 8
BYTE_MASK = 0xFF
WORD_MASK = (1 << 64) - 1
UNSET = -123456
WHITESPACE = " \t\n\r\f\v"
HEX_ROW = re.compile(r"(?:[0-9a-fA-F]{2})+")
BBX = re.compile(r"BBX\s+(-?[0-9]+)\s+(-?[0-9]+)\s+(-?[0-9]+)\s+(-?[0-9]+)")
ENCODING = re.compile(r"ENCODING +(.*)")
INTEGER = re.compile(r"[+-]?[0-9]+")
METRICS = {
    "ascent": re.compile(r'FONT_ASCENT\s+"?([0-9]+)"?'),
    "descent": re.compile(r'FONT_DESCENT\s+"?([0-9]+)"?'),
    "average_width": re.compile(r'AVERAGE_WIDTH\s+"?([0-9]+)"?'),
}
CHARS = re.compile(r'CHARS\s+"?([0-9]+)"?')


@dataclass
class GlyphSet:
    """Glyph bitmaps keyed by Unicode value, one list of bytes per glyph."""

    width: int = 0
    height: int = 0
    glyphs: dict[int, list[int]] = field(default_factory=dict)

    @property
    def row_size(self) -> int:
        """The number of bytes one row of a glyph takes."""
        return (self.width + 7) >> 3

    @property
    def matrix_size(self) -> int:
        """The number of bytes a whole glyph takes."""
        return self.row_size * self.height


@dataclass
class _Metrics:
    """The font-wide numbers read before the first glyph."""

    ascent: int = 0
    descent: int = 0
    average_width: int = 0


@dataclass
class _Placement:
    """Where a glyph's rows sit inside the cell, from its BBX line."""

    before: int
    after: int
    shift: int


@dataclass
class _Glyph:
    """The glyph being read."""

    encoding: int = UNSET
    unusable: bool = False
    rows: int = 0
    truncated: bool = False
    placement: _Placement | None = None
    data: list[int] = field(default_factory=list)


def split_lines(text: str) -> list[str]:
    """Return the lines of *text* with surrounding whitespace removed."""
    return [line.strip(WHITESPACE) for line in text.split("\n")]


class BdfReader:
    """Read one BDF file into a :class:`GlyphSet`: first the header, then the glyphs."""

    def __init__(self, name: str, text: str, target: GlyphSet, warn: Callable[[str], None]) -> None:
        """Prepare to read the font *text*, called *name*, into *target*; problems go to *warn*."""
        self._path = name
        self._target = target
        self._warn = warn
        self._metrics = _Metrics()
        self._glyph = _Glyph()
        self._number = 0
        self._lines: Iterator[tuple[int, str]] = enumerate(split_lines(text), start=1)

    def read_header(self) -> None:
        """Read the header up to and including CHARS, and set or check the cell size."""
        for _, line in self._lines:
            for name, pattern in METRICS.items():
                found = pattern.fullmatch(line)
                if found:
                    setattr(self._metrics, name, int(found.group(1)))
            if CHARS.fullmatch(line):
                break
        self._check_height()
        self._check_width()

    def read_glyphs(self) -> None:
        """Read the glyphs that follow the header."""
        for number, line in self._lines:
            self._number = number
            if self._read_line(line):
                break

    def _fail(self, message: str) -> FontFormatError:
        """Return the error to raise for a problem in this file."""
        return FontFormatError(f"{self._path}: {message}")

    def _check_height(self) -> None:
        """Set the cell height from the first font and require later fonts to agree."""
        target = self._target
        height = self._metrics.ascent + self._metrics.descent
        if target.height and target.height != height:
            message = "the height is not the same as in the previous font."
            raise self._fail(message)
        if not target.height:
            if not 0 < height <= MAX_HEIGHT:
                message = f"height {height} zero or too big"
                raise self._fail(message)
            target.height = height

    def _check_width(self) -> None:
        """Set the cell width from the first font and require later fonts to agree."""
        target = self._target
        average = self._metrics.average_width
        if target.width:
            if target.width * WIDTH_DIVISOR != average:
                message = "the width is not the same as in the previous font."
                raise self._fail(message)
            return
        if average % WIDTH_DIVISOR:
            message = "the width is not integer number."
            raise self._fail(message)
        width = average // WIDTH_DIVISOR
        if not 0 < width <= MAX_WIDTH:
            message = f"width {width} zero or too big"
            raise self._fail(message)
        target.width = width

    def _read_line(self, line: str) -> bool:
        """Handle one line after the header; return True at ENDFONT."""
        if line.startswith("STARTCHAR"):
            self._glyph = _Glyph()
            return False
        box = BBX.fullmatch(line)
        if box:
            self._start_box(*(int(group) for group in box.groups()))
        elif ENCODING.match(line):
            self._set_encoding(line)
        elif HEX_ROW.fullmatch(line):
            self._add_row(line)
        elif line.startswith("ENDCHAR"):
            self._end_glyph()
        return line == "ENDFONT"

    def _start_box(self, width: int, height: int, x_offset: int, y_offset: int) -> None:
        """Record where this glyph's rows sit inside the cell."""
        metrics = self._metrics
        row_size = self._target.row_size
        self._glyph.placement = _Placement(
            before=(metrics.ascent - y_offset - height) * row_size,
            after=(metrics.descent + y_offset) * row_size,
            shift=(row_size - ((width + 7) >> 3)) * BITS_PER_BYTE - x_offset,
        )

    def _set_encoding(self, line: str) -> None:
        """Remember the code point of the glyph."""
        value = ENCODING.match(line)
        text = value.group(1) if value else ""
        self._glyph.truncated = False
        if INTEGER.fullmatch(text):
            self._glyph.encoding = int(text)
        else:
            self._glyph.unusable = True

    def _add_row(self, hex_text: str) -> None:
        """Add one bitmap row to the glyph, fitting it to the cell width."""
        glyph = self._glyph
        if glyph.placement is None:
            message = f"no BBX at line {self._number}"
            raise self._fail(message)
        row_size = self._target.row_size
        if len(hex_text) > 2 * row_size:
            if len(hex_text) >= 3 * row_size:
                glyph.rows = UNSET
                return
            if not glyph.truncated:
                self._warn(f"U+{glyph.encoding:04X}: truncating width\n")
                glyph.truncated = True
            hex_text = hex_text[: 2 * row_size]
        row = int(hex_text, 16)
        if glyph.placement.shift > 0:
            row = (row << glyph.placement.shift) & WORD_MASK
        else:
            row >>= -glyph.placement.shift
        for index in range(1, row_size + 1):
            glyph.data.append((row >> (BITS_PER_BYTE * (row_size - index))) & BYTE_MASK)
        glyph.rows += 1

    def _end_glyph(self) -> None:
        """Store the finished glyph unless an earlier font already defined it."""
        glyph, target = self._glyph, self._target
        if glyph.rows < 0:
            return
        placement = glyph.placement or _Placement(0, 0, 0)
        expected = target.height - (placement.before + placement.after) // target.row_size
        if glyph.rows != expected:
            message = f"invalid number of rows {glyph.rows} at line {self._number}"
            raise self._fail(message)
        if glyph.encoding == UNSET and not glyph.unusable:
            message = f"missing ENCODING before ENDCHAR at line {self._number}"
            raise self._fail(message)
        if not glyph.unusable and glyph.encoding not in target.glyphs:
            target.glyphs[glyph.encoding] = _fitted(glyph.data, placement)


def _fitted(data: list[int], placement: _Placement) -> list[int]:
    """Return a glyph's bytes padded or trimmed so that they fill the whole cell."""
    before, after = placement.before, placement.after
    if before < 0:
        data = data[-before:]
        before = 0
    if after < 0:
        data = data[: len(data) + after]
        after = 0
    return [0] * before + data + [0] * after


def read_bdf_text(name: str, text: str, target: GlyphSet, warn: Callable[[str], None]) -> None:
    """Read the BDF font *text*, known as *name*, into *target*."""
    reader = BdfReader(name, text, target, warn)
    reader.read_header()
    reader.read_glyphs()


def read_bdf(path: Path, target: GlyphSet, warn: Callable[[str], None]) -> None:
    """Read the BDF at *path* into *target*."""
    read_bdf_text(str(path), path.read_bytes().decode("latin-1"), target, warn)

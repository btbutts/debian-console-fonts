"""Equivalence classes of Unicode values: symbols that may share one glyph.

The classes and their order are built exactly as bdf2psf builds them, because the
order of a class decides which glyph is used and how the Unicode table is written.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from psf_font_maker.bdf2psf.errors import EquivalenceError

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

SPACE = "[ \t\n\r\f\v]"
FIRST_CODE = re.compile(rf"U\+([0-9a-fA-F]{{1,4}}){SPACE}+(.*)")
NEXT_CODE = re.compile(rf"U\+([0-9a-fA-F]+){SPACE}*(.*)")
PRINTABLE_ASCII = range(0x20, 0x7F)
FIRST_HIGH_PRINTABLE = 0xA0
BOX_RANGES = (range(0x2500, 0x2591), range(0x2594, 0x25A0))

# CP437 code -> Unicode, for the symbols the PC character ROM has (8 per line).
_CP437_TEXT = """
fffd 263a 263b 2665 2666 2663 2660 2022
25d8 25cb 25d9 2642 2640 266a 266b 263c
25ba 25c4 2195 203c 00b6 00a7 25ac 21a8
2191 2193 2192 2190 221f 2194 25b2 25bc
0020 0021 0022 0023 0024 0025 0026 0027
0028 0029 002a 002b 002c 002d 002e 002f
0030 0031 0032 0033 0034 0035 0036 0037
0038 0039 003a 003b 003c 003d 003e 003f
0040 0041 0042 0043 0044 0045 0046 0047
0048 0049 004a 004b 004c 004d 004e 004f
0050 0051 0052 0053 0054 0055 0056 0057
0058 0059 005a 005b 005c 005d 005e 005f
0060 0061 0062 0063 0064 0065 0066 0067
0068 0069 006a 006b 006c 006d 006e 006f
0070 0071 0072 0073 0074 0075 0076 0077
0078 0079 007a 007b 007c 007d 007e 007f
00c7 00fc 00e9 00e2 00e4 00e0 00e5 00e7
00ea 00eb 00e8 00ef 00ee 00ec 00c4 00c5
00c9 00e6 00c6 00f4 00f6 00f2 00fb 00f9
00ff 00d6 00dc 00a2 00a3 00a5 20a7 0192
00e1 00ed 00f3 00fa 00f1 00d1 00aa 00ba
00bf 2310 00ac 00bd 00bc 00a1 00ab 00bb
2591 2592 2593 2502 2524 2561 2562 2556
2555 2563 2551 2557 255d 255c 255b 2510
2514 2534 252c 251c 2500 253c 255e 255f
255a 2554 2569 2566 2560 2550 256c 2567
2568 2564 2565 2559 2558 2552 2553 256b
256a 2518 250c 2588 2584 258c 2590 2580
03b1 00df 0393 03c0 03a3 03c3 00b5 03c4
03a6 0398 03a9 03b4 221e 03c6 03b5 2229
2261 00b1 2265 2264 2320 2321 00f7 2248
00b0 2219 00b7 221a 207f 00b2 25a0 00a0
"""
CP437 = tuple(int(word, 16) for word in _CP437_TEXT.split())
UNICODE_TO_CP437 = {unicode: code for code, unicode in enumerate(CP437)}


def printable(code: int) -> bool:
    """Return True if *code* is a printable symbol."""
    return code in PRINTABLE_ASCII or code >= FIRST_HIGH_PRINTABLE


def file_lines(path: Path) -> list[str]:
    """Return the lines of *path*, each ending in a newline except possibly the last."""
    text = path.read_bytes().decode("latin-1")
    pieces = text.split("\n")
    lines = [piece + "\n" for piece in pieces[:-1]]
    if pieces[-1]:
        lines.append(pieces[-1])
    return lines


def meaningful(lines: Iterable[str]) -> Iterable[tuple[int, str]]:
    """Yield the numbered lines that have content once comments are removed."""
    for number, line in enumerate(lines, start=1):
        text = re.sub(r"#.*", "", line)
        text = re.sub(rf"^{SPACE}*", "", text)
        if text:
            yield number, text


class Equivalence:
    """The classes of symbols considered equal, as lists shared by their members."""

    def __init__(self) -> None:
        """Start with no classes."""
        self._classes: dict[int, list[int]] = {}

    def of(self, code: int) -> list[int]:
        """Return the class containing *code*, creating a one-member class if needed."""
        if code not in self._classes:
            self._classes[code] = [code]
        return self._classes[code]

    def is_box_drawings(self, code: int) -> bool:
        """Return True if *code* or an equivalent symbol is a box-drawing character."""
        return any(
            member in area for member in self.of(code) for area in BOX_RANGES
        )

    def cp437(self, code: int) -> int:
        """Return the CP437 position of *code* or an equivalent symbol, or 0."""
        for member in self.of(code):
            if UNICODE_TO_CP437.get(member):
                return UNICODE_TO_CP437[member]
        return 0

    def load(self, path: Path) -> None:
        """Merge the classes listed in an equivalents file."""
        for number, text in meaningful(file_lines(path)):
            head, rest = self._first_printable(text)
            if head == 0:
                continue
            self.of(head)
            rest = self._merge_rest(head, rest)
            if re.match(r".", rest):
                message = f"{path}: syntax error on line {number}: {rest}"
                raise EquivalenceError(message)

    @staticmethod
    def _first_printable(text: str) -> tuple[int, str]:
        """Return the first printable code on the line and the text after it."""
        found = FIRST_CODE.match(text)
        while found:
            code, text = int(found.group(1), 16), found.group(2)
            if printable(code):
                return code, text
            found = FIRST_CODE.match(text)
        return 0, text

    def _merge_rest(self, head: int, text: str) -> str:
        """Merge every later code on the line into the class of *head*."""
        found = NEXT_CODE.match(text)
        while found:
            code, text = int(found.group(1), 16), found.group(2)
            if printable(code):
                self._join(head, code)
            found = NEXT_CODE.match(text)
        return text

    def _join(self, head: int, code: int) -> None:
        """Put *code* into the class of *head*, merging classes when they differ."""
        classes = self._classes
        if code not in classes:
            classes[head].insert(0, code)
            classes[code] = classes[head]
        elif classes[head] is not classes[code]:
            for member in list(classes[code]):
                if not member:
                    break
                classes[head].insert(0, member)
                classes[member] = classes[head]
        else:
            classes[head].insert(0, code)

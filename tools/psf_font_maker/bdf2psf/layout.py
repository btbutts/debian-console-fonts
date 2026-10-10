"""Choose a position in the font for each requested symbol.

This follows bdf2psf's rules: a symbol that exists in CP437 goes to its CP437
position when that is free, glyphs that need the 9th-column copy go to the
positions 0xC0-0xDF where the adapter does it, and the rest fill what is left.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from psf_font_maker.bdf2psf.classify import COPY_8TH, DONT_COPY_8TH, RAW
from psf_font_maker.bdf2psf.equivalence import printable
from psf_font_maker.bdf2psf.errors import LayoutError

if TYPE_CHECKING:
    from collections.abc import Callable

    from psf_font_maker.bdf2psf.bdf_reader import GlyphSet
    from psf_font_maker.bdf2psf.classify import Classification
    from psf_font_maker.bdf2psf.equivalence import Equivalence

TAKEN = 0
# The FreeBSD mouse driver draws its cursor with these positions.
FREEBSD_MOUSE = frozenset({0x03, 0x04, 0x05, 0x06})
COPY_RANGES = (range(0xC0, 0xE0), range(0x1C0, 0x1E0))


class Layout:
    """The positions of a font and the symbols assigned to them."""

    def __init__(
        self,
        glyph_set: GlyphSet,
        kinds: Classification,
        font_type: int,
        font_size: int,
        warn: Callable[[str], None],
    ) -> None:
        """Start with every position free and the glyph kinds known."""
        self.glyph_set = glyph_set
        self.kinds = kinds
        self.font_type = font_type
        self.font_size = font_size
        self.warn = warn
        self.classes: list[list[int] | None] = [None] * font_size
        self._kind = [DONT_COPY_8TH] * font_size
        for area in COPY_RANGES:
            for position in area:
                if position < font_size:
                    self._kind[position] = COPY_8TH

    def free_positions(self) -> int:
        """Return how many positions are still free."""
        return sum(1 for kind in self._kind if kind != TAKEN)

    def place(self, code: int, equivalence: Equivalence, wanted: int | None) -> int:
        """Take a free position for the glyph of *code*; *wanted* is the kind it needs."""
        broken = self.kinds.broken_pixels.get(code)
        if broken:
            self.warn(f"U+{code:04X}: {broken} broken pixel(s)\n")
        position = self._cp437_position(equivalence.cp437(code))
        if position is None:
            position = self._first_free(self._skips_mouse, wanted)
        if position is None and wanted is not None:
            self.warn(f"U+{code:04X}: can not be positioned properly\n")
            position = self._first_free(self._skips_mouse, None)
        if position is None:
            position = self._first_free(_never, None)
        if position is None:
            message = "Internal error"
            raise LayoutError(message)
        self._kind[position] = TAKEN
        return position

    def _cp437_position(self, cp437: int) -> int | None:
        """Return the CP437 position if the symbol has one and it is free."""
        if cp437 and self._kind[cp437] != TAKEN:
            return cp437
        return None

    def _skips_mouse(self, position: int) -> bool:
        """Return True if a raw font must not use *position*."""
        return self.font_type == RAW and position in FREEBSD_MOUSE

    def _first_free(self, skip: Callable[[int], bool], wanted: int | None) -> int | None:
        """Return the first free position of kind *wanted* (any kind if None)."""
        for position, kind in enumerate(self._kind):
            if skip(position) or kind == TAKEN:
                continue
            if wanted is None or kind == wanted:
                return position
        return None


def _never(_position: int) -> bool:
    """Return False: no position is skipped."""
    return False


class Assigner:
    """Walk the requested symbols and give each a position."""

    def __init__(
        self,
        layout: Layout,
        equivalence: Equivalence,
        quiet: set[int],
    ) -> None:
        """Prepare to place symbols; *quiet* lists the ones that may be missing silently."""
        self.layout = layout
        self.equivalence = equivalence
        self.quiet = quiet
        self.positioned: set[int] = set()
        self.delayed: list[int] = []

    def place_requested(self, requested: list[int]) -> None:
        """Place the requested symbols whose position depends on the kind of glyph."""
        for code in requested:
            if code in self.positioned or not printable(code):
                continue
            found = self._place_symbol(code)
            if code not in self.quiet and code not in self.positioned:
                reason = "no space in the font" if found else "no glyph defined"
                self.layout.warn(f"U+{code:04X}: {reason}\n")

    def place_delayed(self) -> None:
        """Place the glyphs that can go anywhere, in the positions that are left."""
        for member in self.delayed:
            self._put(member, None)

    def _put(self, code: int, wanted: int | None) -> None:
        """Give *code* a position and record its equivalence class there."""
        position = self.layout.place(code, self.equivalence, wanted)
        self.layout.classes[position] = self.equivalence.of(code)

    def _place_symbol(self, code: int) -> bool:
        """Place the glyph for *code*; return True if any equivalent has a glyph."""
        layout = self.layout
        if len(self.delayed) >= layout.free_positions():
            return False
        for member in self.equivalence.of(code):
            if member in layout.glyph_set.glyphs:
                self._place_member(member)
                self.positioned.update(self.equivalence.of(code))
                return True
        if layout.font_type == RAW:
            self._put(code, DONT_COPY_8TH)
            self.positioned.update(self.equivalence.of(code))
        return False

    def _place_member(self, member: int) -> None:
        """Place the glyph of *member* according to its kind."""
        kind = self.layout.kinds.types[member]
        if kind in {DONT_COPY_8TH, COPY_8TH}:
            self._put(member, kind)
        elif self.equivalence.cp437(member):
            self._put(member, None)
        else:
            self.delayed.append(member)


def assign(
    layout: Layout, equivalence: Equivalence, quiet: set[int], requested: list[int]
) -> None:
    """Give every requested symbol a position; *quiet* ones may be missing silently."""
    assigner = Assigner(layout, equivalence, quiet)
    assigner.place_requested(requested)
    assigner.place_delayed()

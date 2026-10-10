"""Rasterise a font with FreeType the way the C otf2bdf did."""

from __future__ import annotations

import contextlib
import ctypes.util
import importlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.otf2bdf.crop import crop_bitmap
from psf_font_maker.otf2bdf.errors import RenderError
from psf_font_maker.otf2bdf.glyphs import (
    FontInfo,
    GlyphBox,
    RenderedFont,
    RenderedGlyph,
    Size,
    Vertical,
)
from psf_font_maker.otf2bdf.library import LIBRARY_DIR_ENV, library_files
from psf_font_maker.otf2bdf.tables import read_hhea

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from types import ModuleType

# FreeType 2.13.2 and older hint some glyphs differently (a pixel here and there). 2.13.3
# (Debian 13) and 2.14.3 (Buildroot) give identical glyphs.
MINIMUM_FREETYPE = (2, 13, 3)
# Homebrew keeps its libraries where macOS does not look for them by default.
MACOS_LIBRARY_DIRS = "/opt/homebrew/lib:/usr/local/lib"
PLATFORM_MICROSOFT = 3
ENCODING_UNICODE = 1
ENCODING_SYMBOL = 0
LAST_CODE = 0xFFFF  # codes below this are tried
POINT_UNITS = 64
SWIDTH_SCALE = 72000.0
ADVANCE_SHIFT = 6
SHORT_MODULUS = 1 << 16
SHORT_SIGN = 1 << 15
WIDTH_UNKNOWN = 0xFFFF
AVERAGE_ROUNDING = 0.5
AVERAGE_SCALE = 10.0


def add_homebrew_to_library_path() -> None:
    """Let freetype-py find Homebrew's libfreetype on macOS.

    freetype-py loads the FreeType shared library by name through the system loader. On
    Linux that needs no help, because the loader knows the system's library directories.
    macOS does not search Homebrew's, so they are added unless the user set their own.
    """
    if sys.platform == "darwin":
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", MACOS_LIBRARY_DIRS)


def use_library_dir(directory: Path) -> None:
    """Make the next ``load_freetype`` use the FreeType library in *directory*.

    This is passed in the environment, so that worker processes started later use it too.
    """
    os.environ[LIBRARY_DIR_ENV] = str(directory)


@contextlib.contextmanager
def chosen_library() -> Generator[None]:
    """Make freetype-py find the library in the directory set by ``use_library_dir``.

    freetype-py asks ``ctypes.util.find_library`` for the library when it is imported; for
    that moment the answer is the file in the chosen directory.
    """
    directory = os.environ.get(LIBRARY_DIR_ENV)
    if not directory:
        yield
        return
    files = library_files(Path(directory))
    if not files:
        message = f"no FreeType library (libfreetype) in {directory}"
        raise RenderError(message)
    original = ctypes.util.find_library

    def find_library(name: str) -> str | None:
        """Answer for FreeType with the chosen file, for anything else as usual."""
        return str(files[0]) if name == "freetype" else original(name)

    ctypes.util.find_library = find_library
    try:
        yield
    finally:
        ctypes.util.find_library = original


def load_freetype() -> ModuleType:
    """Import the freetype-py package (a module called ``freetype``) and vet its FreeType.

    The import is done here, not at the top of the file, so that the rest of psf_font_maker
    works without freetype-py; only rendering a TrueType font needs it.
    """
    add_homebrew_to_library_path()
    try:
        with chosen_library():
            module = importlib.import_module("freetype")
    except ImportError as exc:
        message = "rendering TrueType fonts needs the freetype-py package (pip install freetype-py)"
        raise RenderError(message) from exc
    version = tuple(module.version())
    if version < MINIMUM_FREETYPE:
        found = ".".join(str(part) for part in version)
        wanted = ".".join(str(part) for part in MINIMUM_FREETYPE)
        message = (
            f"FreeType {found} is too old: it draws some glyphs differently from {wanted} and "
            "later. Run `make freetype` to find or build a suitable one; if freetype-py came "
            "as a wheel it brings its own old FreeType and ignores the system's, so install it "
            "from source instead: pip install --no-binary freetype-py freetype-py"
        )
        raise RenderError(message)
    return module


def trunc_div(numerator: int, denominator: int) -> int:
    """Divide like C: the quotient is rounded towards zero."""
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


def as_short(value: int) -> int:
    """Wrap *value* into a signed 16-bit integer, as C's short does."""
    return (value + SHORT_SIGN) % SHORT_MODULUS - SHORT_SIGN


class Renderer:
    """Render the glyphs of one font at one size."""

    def __init__(self, path: Path, size: Size) -> None:
        """Open the font at *path* and set the size to render at."""
        self._path = path
        self._size = size
        self._ft = load_freetype()
        try:
            self._face = self._ft.Face(str(path))
            self._face.set_char_size(
                0, size.point_size * POINT_UNITS, size.resolution, size.resolution
            )
        except self._ft.FT_Exception as exc:
            message = f"{path}: {exc}"
            raise RenderError(message) from exc
        self._has_cmap = self._select_charmap()

    def _select_charmap(self) -> bool:
        """Choose the Microsoft Unicode character map (or symbol map); False if neither exists."""
        for encoding in (ENCODING_UNICODE, ENCODING_SYMBOL):
            for charmap in self._face.charmaps:
                if charmap.platform_id == PLATFORM_MICROSOFT and charmap.encoding_id == encoding:
                    self._face.set_charmap(charmap)
                    return True
        return False

    def ascent_and_descent(self) -> tuple[int, int]:
        """Return FONT_ASCENT and FONT_DESCENT: the font's hhea values scaled to the size."""
        ascender, descender = read_hhea(self._path)
        units = self._face.units_per_EM
        ppem = self._face.size.y_ppem
        return trunc_div(ascender * ppem, units), -trunc_div(descender * ppem, units)

    def _indices(self) -> Iterator[tuple[int, int]]:
        """Yield (code, glyph index) for every glyph that can be drawn."""
        for code in range(LAST_CODE):
            if self._has_cmap:
                index = self._face.get_char_index(code)
            elif code >= self._face.num_glyphs:
                return
            else:
                index = code
            if index > 0:
                yield code, index

    def _draw(self, code: int, index: int) -> RenderedGlyph | None:
        """Render one glyph; return None if FreeType cannot."""
        ft, face = self._ft, self._face
        try:
            face.load_glyph(index, ft.FT_LOAD_DEFAULT)
            face.glyph.render(ft.FT_RENDER_MODE_MONO)
        except ft.FT_Exception:
            return None
        bitmap = face.glyph.bitmap
        crop = crop_bitmap(bytes(bitmap.buffer), bitmap.width, bitmap.rows, bitmap.pitch)
        advance = face.glyph.metrics.horiAdvance >> ADVANCE_SHIFT
        scale = float(self._size.resolution * self._size.point_size)
        return RenderedGlyph(
            code=code,
            scalable_width=as_short(int((advance * SWIDTH_SCALE) / scale)),
            advance=advance,
            box=GlyphBox(
                width=crop.width,
                height=crop.height,
                x_offset=crop.left + face.glyph.bitmap_left,
                y_offset=crop.top + face.glyph.bitmap_top - bitmap.rows,
            ),
            rows=crop.rows,
        )

    def render(self) -> RenderedFont:
        """Render every glyph of the font and gather the numbers for the BDF header."""
        ft, face = self._ft, self._face
        ascent, descent = self.ascent_and_descent()
        info = FontInfo(
            file_name=self._path.name,
            family=_text(face.family_name) or "Unknown",
            bold=bool(face.style_flags & ft.FT_STYLE_FLAG_BOLD),
            italic=bool(face.style_flags & ft.FT_STYLE_FLAG_ITALIC),
            freetype_version=".".join(str(part) for part in ft.version()),
        )
        font = RenderedFont(info, self._size, Vertical(ascent, descent))
        total_width = 0
        previous = WIDTH_UNKNOWN
        for code, index in self._indices():
            glyph = self._draw(code, index)
            if glyph is None:
                continue
            font.glyphs.append(glyph)
            if previous != WIDTH_UNKNOWN and font.monospaced and glyph.box.width + 1 != previous:
                font.monospaced = False
            previous = glyph.box.width
            total_width += glyph.box.width
            _grow(font, glyph)
        if not font.glyphs:
            message = f"no glyphs generated from {self._path}"
            raise RenderError(message)
        average = total_width / len(font.glyphs)
        font.average_width = int((average + AVERAGE_ROUNDING) * AVERAGE_SCALE)
        return font


def _text(name: bytes | str | None) -> str:
    """Return a name from FreeType as text; older freetype-py versions give bytes."""
    if isinstance(name, bytes):
        return name.decode("latin-1")
    return name or ""


def _grow(font: RenderedFont, glyph: RenderedGlyph) -> None:
    """Widen the font's bounding box to take in *glyph*."""
    box = font.box
    place = glyph.box
    box.max_ascent = max(box.max_ascent, place.height + place.y_offset)
    box.max_descent = max(box.max_descent, -place.y_offset)
    box.max_right = max(box.max_right, place.width + place.x_offset)
    box.min_left = min(box.min_left, place.x_offset)


def render_font(path: Path, size: Size) -> RenderedFont:
    """Render the font at *path* at *size*."""
    return Renderer(path, size).render()

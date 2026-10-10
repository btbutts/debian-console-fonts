"""Convert BDF fonts to a PSF font: the work of console-setup's ``bdf2psf``."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from psf_font_maker.bdf2psf import output
from psf_font_maker.bdf2psf.bdf_reader import GlyphSet, read_bdf, read_bdf_text
from psf_font_maker.bdf2psf.classify import RAW, TEXT_MODE, classify
from psf_font_maker.bdf2psf.equivalence import Equivalence, file_lines, meaningful
from psf_font_maker.bdf2psf.errors import ConversionError, EquivalenceError
from psf_font_maker.bdf2psf.layout import Layout, assign

MAX_POSITIONS = 2048
SMALL_FONT = 256
LARGE_FONT = 512
SYMBOL_LINE = re.compile(r"U\+([0-9a-fA-F]+)[ \t\n\r\f\v]*")


@dataclass
class BdfText:
    """A BDF font that exists only as text, for example one rendered from a TrueType font."""

    name: str
    text: str


@dataclass
class Request:
    """What to build: the inputs, the kind of font and its number of positions."""

    bdfs: list[Path | BdfText]
    equivalents: list[Path]
    symbols: list[str]
    font_size: int
    font_type: int = TEXT_MODE
    echo: bool = True
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        """Record a warning and, unless told not to, print it."""
        self.warnings.append(message)
        if self.echo:
            sys.stderr.write(f"WARNING: {message}")


def normalise_size(font_type: int, size: int) -> int:
    """Return the number of positions to use, rejecting impossible sizes."""
    if size <= SMALL_FONT:
        size = SMALL_FONT
    elif size <= LARGE_FONT:
        size = LARGE_FONT
    message = ""
    if not 0 < size <= MAX_POSITIONS:
        message = f"zero or too many characters in the PSF font ({size})"
    elif font_type == TEXT_MODE and size > LARGE_FONT:
        message = f"too many characters in non-framebuffer PSF font ({size})"
    elif font_type == RAW and size > SMALL_FONT:
        message = f"too many characters in in a raw font ({size})"
    if message:
        raise ConversionError(message)
    return size


def read_symbols(spec: str) -> tuple[list[int], set[int]]:
    """Read a symbols file; a leading colon on its name silences missing-symbol warnings."""
    quiet = spec.startswith(":")
    path = Path(spec[1:] if quiet else spec)
    codes: list[int] = []
    for number, text in meaningful(file_lines(path)):
        found = SYMBOL_LINE.fullmatch(text)
        if not found:
            message = f"{path}: syntax error on line {number}: {text}"
            raise EquivalenceError(message)
        codes.append(int(found.group(1), 16))
    return codes, set() if quiet else set(codes)


def build(request: Request) -> Layout:
    """Run the conversion up to a finished layout."""
    size = normalise_size(request.font_type, request.font_size)
    glyph_set = GlyphSet()
    for source in request.bdfs:
        if isinstance(source, BdfText):
            read_bdf_text(source.name, source.text, glyph_set, request.warn)
        else:
            read_bdf(source, glyph_set, request.warn)
    equivalence = Equivalence()
    kinds = classify(glyph_set, request.font_type, equivalence)
    for path in request.equivalents:
        equivalence.load(path)
    layout = Layout(glyph_set, kinds, request.font_type, size, request.warn)
    requested: list[int] = []
    loud: set[int] = set()
    for spec in request.symbols:
        codes, warned = read_symbols(spec)
        requested.extend(codes)
        loud |= warned
    assign(layout, equivalence, set(requested) - loud, requested)
    return layout


def convert(request: Request) -> bytes:
    """Return the PSF font for *request*."""
    return output.encode(build(request))

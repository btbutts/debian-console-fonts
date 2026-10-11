"""Find the font sources on disk and describe the BDF fonts a face is made from."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from time import monotonic
from typing import TYPE_CHECKING

from psf_font_maker.bdf2psf.convert import BdfText
from psf_font_maker.bdf_double.enlarge import convert as enlarge
from psf_font_maker.common.errors import ToolError
from psf_font_maker.common.log import detail
from psf_font_maker.common.manifest import Manifest
from psf_font_maker.otf2bdf.bdf_text import to_bdf
from psf_font_maker.otf2bdf.glyphs import Size
from psf_font_maker.otf2bdf.render import render_font

if TYPE_CHECKING:
    from pathlib import Path

DEJAVU = "dejavu"
TRUETYPE_DIR = "ttf"  # inside the DejaVu directory
RESOLUTION = 115  # dpi that makes a point size of N come out N pixels wide for DejaVu Mono
SPACING = "C"
CODESETS_DIR = "codesets"
# The sources (names in sources.json) that hold BDF fonts.
BDF_HOMES = ("terminus-font", "ucs-fonts", "uni-vga", "debian-legacy-fonts")


class SourcesError(ToolError):
    """The font sources are missing or incomplete."""


class SourceTree:
    """The tables in the data directory, and the font sources that ``sources.json`` locates."""

    def __init__(self, data: Path, manifest: Manifest) -> None:
        """Check that the data directory has the code set tables."""
        self.data = data
        self.manifest = manifest
        if not (data / CODESETS_DIR).is_dir():
            message = f"{data} has no font tables; is the data directory right?"
            raise SourcesError(message)

    def bdf(self, name: str) -> Path:
        """Return the path of BDF font *name*, which is in one of the font directories."""
        homes = [self.manifest.entry(home).directory for home in BDF_HOMES]
        for home in homes:
            if (home / name).is_file():
                return home / name
        places = ", ".join(str(home) for home in homes)
        message = f"BDF font {name} not found in {places}; fetch the sources first (see README.md)"
        raise SourcesError(message)

    def truetype_dir(self) -> Path:
        """Return the directory of the DejaVu TrueType files."""
        return self.manifest.entry(DEJAVU).directory / TRUETYPE_DIR

    def data_file(self, name: str) -> Path:
        """Return one of the data files (equivalents, symbol sets)."""
        return self.data / name

    def codeset_file(self, codeset: str) -> Path:
        """Return the symbol list of a code set; its extension is the number of positions."""
        found = sorted((self.data / CODESETS_DIR).glob(f"{codeset}.*"))
        if not found:
            message = f"no symbol list for code set {codeset} in {self.data / CODESETS_DIR}"
            raise SourcesError(message)
        return found[0]


@cache
def rendered_text(ttf: Path, cell: int) -> str:
    """Render a TrueType font at cell width *cell* and return it as BDF text."""
    detail(f"rendering {ttf.name} at cell width {cell} with FreeType")
    started = monotonic()
    text = to_bdf(render_font(ttf, Size(cell, RESOLUTION)), SPACING, cell)
    detail(f"rendered {ttf.name} at cell width {cell} in {monotonic() - started:.1f}s")
    return text


@dataclass(frozen=True)
class BdfSpec:
    """One BDF font a face is made from: a file, or one that is generated."""

    name: str
    path: Path | None = None
    ttf: Path | None = None
    cell: int = 0
    doubled: bool = False

    def text(self) -> str:
        """Return the BDF text of the font."""
        if self.ttf is not None:
            return rendered_text(self.ttf, self.cell)
        if self.path is None:
            message = f"{self.name}: no file or font to take it from"
            raise SourcesError(message)
        text = self.path.read_bytes().decode("latin-1")
        return enlarge(text, self.path.name) if self.doubled else text

    def load(self) -> Path | BdfText:
        """Return what bdf2psf reads: the file itself, or the text of a generated font."""
        if self.ttf is None and not self.doubled and self.path is not None:
            return self.path
        return BdfText(self.name, self.text())

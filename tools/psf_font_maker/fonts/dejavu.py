"""The DejaVu console faces, rendered from the TrueType files."""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from psf_font_maker.fonts.sources import RESOLUTION, BdfSpec
from psf_font_maker.otf2bdf.glyphs import Size
from psf_font_maker.otf2bdf.render import Renderer

if TYPE_CHECKING:
    from pathlib import Path

    from psf_font_maker.fonts.options import DejaVuOptions

HEIGHT_FONT = "DejaVuSansMono"
MONO = {
    "DejaVu": "DejaVuSansMono",
    "DejaVuBold": "DejaVuSansMono-Bold",
    "DejaVuOblique": "DejaVuSansMono-Oblique",
    "DejaVuBoldOblique": "DejaVuSansMono-BoldOblique",
}
PROPORTIONAL = {
    "DejaVuSans": "DejaVuSans",
    "DejaVuSansBold": "DejaVuSans-Bold",
    "DejaVuSansOblique": "DejaVuSans-Oblique",
    "DejaVuSansBoldOblique": "DejaVuSans-BoldOblique",
    "DejaVuSansExtraLight": "DejaVuSans-ExtraLight",
    "DejaVuSansCondensed": "DejaVuSansCondensed",
    "DejaVuSansCondensedBold": "DejaVuSansCondensed-Bold",
    "DejaVuSansCondensedOblique": "DejaVuSansCondensed-Oblique",
    "DejaVuSansCondensedBoldOblique": "DejaVuSansCondensed-BoldOblique",
    "DejaVuSerif": "DejaVuSerif",
    "DejaVuSerifBold": "DejaVuSerif-Bold",
    "DejaVuSerifItalic": "DejaVuSerif-Italic",
    "DejaVuSerifBoldItalic": "DejaVuSerif-BoldItalic",
    "DejaVuSerifCondensed": "DejaVuSerifCondensed",
    "DejaVuSerifCondensedBold": "DejaVuSerifCondensed-Bold",
    "DejaVuSerifCondensedItalic": "DejaVuSerifCondensed-Italic",
    "DejaVuSerifCondensedBoldItalic": "DejaVuSerifCondensed-BoldItalic",
    "DejaVuMath": "DejaVuMathTeXGyre",
}
PREFIX = "DejaVu"


@cache
def cell_height(ttf: Path, cell: int) -> int:
    """Return the height of the cell at width *cell*: the font's ascent plus its descent."""
    ascent, descent = Renderer(ttf, Size(cell, RESOLUTION)).ascent_and_descent()
    return ascent + descent


def styles(options: DejaVuOptions) -> dict[str, str]:
    """Return the face style names and the TrueType files they come from."""
    return {**MONO, **(PROPORTIONAL if options.proportional else {})}


def dejavu_faces(directory: Path, options: DejaVuOptions) -> dict[str, BdfSpec]:
    """Return the DejaVu faces (like ``DejaVuBold59x32``) made from the files in *directory*."""
    height_font = directory / f"{HEIGHT_FONT}.ttf"
    faces: dict[str, BdfSpec] = {}
    for cell in options.sizes:
        height = cell_height(height_font, cell)
        for style, file_name in styles(options).items():
            spec = BdfSpec(
                name=f"dejavu-{style}-{cell}.bdf", ttf=directory / f"{file_name}.ttf", cell=cell
            )
            faces[f"{style}{height}x{cell}"] = spec
    return faces

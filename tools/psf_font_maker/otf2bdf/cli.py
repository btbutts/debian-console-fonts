"""The ``otf2bdf`` command: render a TrueType or OpenType font as BDF."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.otf2bdf.bdf_text import to_bdf
from psf_font_maker.otf2bdf.glyphs import Size
from psf_font_maker.otf2bdf.render import Renderer, render_font

if TYPE_CHECKING:
    import argparse

NAME = "otf2bdf"
HELP = "render a TrueType/OpenType font to BDF (a port of otf2bdf)"


def declare(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of the command."""
    parser.add_argument("font", type=Path, help="the .ttf or .otf file")
    parser.add_argument("-p", "--point-size", type=int, default=Size.point_size)
    parser.add_argument("-r", "--resolution", type=int, default=Size.resolution, help="dpi")
    parser.add_argument(
        "-c",
        "--spacing",
        choices=("P", "M", "C", "p", "m", "c"),
        help="XLFD spacing letter (default: M or P from the glyph widths)",
    )
    parser.add_argument(
        "--cell-width",
        type=int,
        help="set AVERAGE_WIDTH to ten times this, as console-setup does for its cell size",
    )
    parser.add_argument(
        "--height",
        action="store_true",
        help="print FONT_ASCENT plus FONT_DESCENT (the cell height) and stop",
    )
    parser.add_argument("-o", "--output", type=Path, help="write here instead of standard output")


def run(args: argparse.Namespace) -> int:
    """Carry out the command."""
    size = Size(args.point_size, args.resolution)
    if args.height:
        ascent, descent = Renderer(args.font, size).ascent_and_descent()
        print(ascent + descent)
        return 0
    text = to_bdf(render_font(args.font, size), args.spacing, args.cell_width)
    if args.output:
        args.output.write_text(text, encoding="latin-1")
    else:
        sys.stdout.write(text)
    return 0

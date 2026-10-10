"""The ``bdf2psf`` command: the same arguments as console-setup's Perl tool."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.bdf2psf import output
from psf_font_maker.bdf2psf.classify import FRAMEBUFFER, RAW, TEXT_MODE
from psf_font_maker.bdf2psf.convert import Request, build

if TYPE_CHECKING:
    import argparse

NAME = "bdf2psf"
HELP = "convert BDF fonts to a PSF font (console-setup's bdf2psf)"
SEPARATOR = "+"


def declare(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of the command."""
    kind = parser.add_mutually_exclusive_group()
    kind.add_argument("--fb", action="store_true", help="create a framebuffer font")
    kind.add_argument("--raw", action="store_true", help="create a raw font (size*8 bytes)")
    parser.add_argument("--log", type=Path, help="file for the warnings")
    parser.add_argument("bdfs", help="BDF{+BDF}: fonts listed first take precedence")
    parser.add_argument("equivalents", help="EQUIV{+EQUIV}: files of equivalent symbols")
    parser.add_argument("symbols", help="SYMB{+[:]SYMB}: symbols to include, in priority order")
    parser.add_argument("size", type=int, help="number of positions (256 or 512 usually)")
    parser.add_argument("psf", type=Path, help="the font to write")
    parser.add_argument("sfm", nargs="?", type=Path, help="also write the symbol table here")


def run(args: argparse.Namespace) -> int:
    """Carry out the command."""
    font_type = RAW if args.raw else FRAMEBUFFER if args.fb else TEXT_MODE
    request = Request(
        bdfs=[Path(item) for item in args.bdfs.split(SEPARATOR)],
        equivalents=[Path(item) for item in args.equivalents.split(SEPARATOR)],
        symbols=args.symbols.split(SEPARATOR),
        font_size=args.size,
        font_type=font_type,
    )
    layout = build(request)
    args.psf.write_bytes(output.encode(layout))
    if args.sfm:
        args.sfm.write_text(output.sfm_text(layout), encoding="latin-1")
    if args.log:
        args.log.write_text("".join(f"WARNING: {text}" for text in request.warnings))
    return 0

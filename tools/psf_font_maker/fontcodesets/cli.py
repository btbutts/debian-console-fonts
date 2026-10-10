"""The ``fontcodesets`` command: the code sets some BDF fonts support."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.fontcodesets.coverage import font_symbols, supported_sets

if TYPE_CHECKING:
    import argparse

NAME = "fontcodesets"
HELP = "print the code sets that BDF fonts support (console-setup's fontcodesets)"
SEPARATOR = "+"


def declare(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of the command."""
    parser.add_argument("bdfs", help="BDF{+BDF}: names of fonts inside the BDF directory")
    parser.add_argument(
        "--bdf-dir",
        type=Path,
        default=Path("bdf"),
        help="directory the font names are relative to (default: bdf)",
    )


def run(args: argparse.Namespace) -> int:
    """Carry out the command: print each supported set followed by a space."""
    sys.stderr.write(f"fontcodesets {args.bdfs}\n")
    paths = [args.bdf_dir / name for name in args.bdfs.split(SEPARATOR)]
    names = supported_sets(font_symbols(paths))
    sys.stdout.write("".join(f"{name} " for name in names) + "\n")
    return 0

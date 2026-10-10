"""The ``bdf-double`` command."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.bdf_double.enlarge import convert

if TYPE_CHECKING:
    import argparse

NAME = "bdf-double"
HELP = "enlarge a BDF font by 2x and print it"


def declare(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of the command."""
    parser.add_argument("bdf", type=Path, help="the BDF font to enlarge")


def run(args: argparse.Namespace) -> int:
    """Write the enlargement of the font to standard output."""
    sys.stdout.write(convert(args.bdf.read_text(encoding="latin-1"), args.bdf.name))
    return 0

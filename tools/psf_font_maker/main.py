"""Command line entry point: ``python3 -m psf_font_maker <tool> ...``.

Each tool lives in its own sub-package and offers a ``cli`` module with ``NAME``,
``HELP``, ``declare(parser)`` and ``run(args)``; this module only collects them.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from psf_font_maker import __version__
from psf_font_maker.bdf2psf import cli as bdf2psf_cli
from psf_font_maker.bdf_double import cli as bdf_double_cli
from psf_font_maker.common.errors import ToolError
from psf_font_maker.compare_fonts import cli as compare_fonts_cli
from psf_font_maker.fontcodesets import cli as fontcodesets_cli
from psf_font_maker.fonts import cli as fonts_cli
from psf_font_maker.freetype_lib import cli as freetype_cli
from psf_font_maker.otf2bdf import cli as otf2bdf_cli

if TYPE_CHECKING:
    from collections.abc import Sequence

TOOLS = (
    fonts_cli,
    freetype_cli,
    bdf2psf_cli,
    fontcodesets_cli,
    bdf_double_cli,
    compare_fonts_cli,
    otf2bdf_cli,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(prog="psf_font_maker", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for tool in TOOLS:
        sub = subparsers.add_parser(tool.NAME, help=tool.HELP)
        tool.declare(sub)
        sub.set_defaults(handler=tool.run)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line tool and return its exit status."""
    args = parse_args(argv)
    try:
        return args.handler(args)
    except (ToolError, OSError) as exc:
        print(f"psf_font_maker: {exc}", file=sys.stderr)
        return 1

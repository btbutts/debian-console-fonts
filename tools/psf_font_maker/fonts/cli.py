"""The ``fonts`` command: build the console fonts that were asked for."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.common.errors import ToolError
from psf_font_maker.fonts.options import (
    DEFAULT_CODESETS,
    DEFAULT_DEJAVU_SIZES,
    DEFAULT_FACES,
    POOLS,
    DejaVuOptions,
    Options,
)
from psf_font_maker.fonts.plan import Planner
from psf_font_maker.fonts.runner import build_all
from psf_font_maker.otf2bdf.render import use_library_dir

if TYPE_CHECKING:
    import argparse

NAME = "fonts"
HELP = "choose, convert and write console fonts (what `make fonts` runs)"


def words(values: list[str]) -> tuple[str, ...]:
    """Return the words of option values that may each hold several words."""
    return tuple(word for value in values for word in value.split())


def declare_selection(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments that choose the fonts (shared with the ``freetype`` command)."""
    parser.add_argument(
        "--data", type=Path, default=Path("data"), help="the code set tables and face lists"
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("sources.json"),
        help="the manifest that says where each font source is (default: %(default)s)",
    )
    parser.add_argument(
        "--faces",
        nargs="+",
        default=list(DEFAULT_FACES),
        help="face patterns, % standing for any text (default: %(default)s)",
    )
    parser.add_argument(
        "--codesets",
        nargs="+",
        default=list(DEFAULT_CODESETS),
        help="code sets to build (default: %(default)s)",
    )
    parser.add_argument("--skip", nargs="*", default=[], help="face patterns to leave out")
    parser.add_argument("--pool", choices=POOLS, default="good", help="which faces to offer")
    parser.add_argument(
        "--dejavu-sizes",
        nargs="+",
        default=[str(size) for size in DEFAULT_DEJAVU_SIZES],
        help="cell widths to render DejaVu at (default: %(default)s)",
    )
    parser.add_argument(
        "--dejavu-proportional", action="store_true", help="also build the proportional faces"
    )


def declare(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of the command."""
    declare_selection(parser)
    parser.add_argument("--jobs", type=int, help="processes to use (default: one per CPU)")
    parser.add_argument(
        "--freetype-lib-dir",
        type=Path,
        help="directory holding the libfreetype to render TrueType fonts with "
        "(`psf_font_maker freetype` finds or builds one)",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--out", type=Path, help="write the fonts into this directory")
    target.add_argument("--list", action="store_true", help="only list the fonts")


def required(name: str, values: list[str]) -> tuple[str, ...]:
    """Return the words of option *name*; it is an error to give none."""
    found = words(values)
    if not found:
        message = f"{name}: select at least one"
        raise ToolError(message)
    return found


def options_from(args: argparse.Namespace) -> Options:
    """Collect the selection options of the command line."""
    return Options(
        data=args.data,
        sources=args.sources,
        faces=required("--faces", args.faces),
        codesets=required("--codesets", args.codesets),
        skip=words(args.skip),
        pool=args.pool,
        dejavu=DejaVuOptions(
            tuple(int(size) for size in required("--dejavu-sizes", args.dejavu_sizes)),
            args.dejavu_proportional,
        ),
    )


def run(args: argparse.Namespace) -> int:
    """Carry out the command."""
    if args.freetype_lib_dir is not None:
        use_library_dir(args.freetype_lib_dir)
    planner = Planner(options_from(args))
    if args.list:
        names = planner.names()
        print("\n".join(names))
        print(f"{len(names)} fonts", file=sys.stderr)
        return 0
    built = build_all(planner.jobs(), args.out, args.jobs)
    print(f"{len(built)} fonts in {args.out}/")
    return 0

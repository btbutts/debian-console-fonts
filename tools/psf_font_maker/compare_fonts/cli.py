"""The ``compare-fonts`` command."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.compare_fonts.compare import compare, font_files, percent

if TYPE_CHECKING:
    import argparse

NAME = "compare-fonts"
HELP = "compare the PSF fonts of two directories glyph by glyph"


def declare(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of the command."""
    parser.add_argument("dir_a", type=Path)
    parser.add_argument("dir_b", type=Path)
    parser.add_argument("--glob", default="*", help="only fonts whose name matches (default: all)")
    parser.add_argument(
        "--min-identical",
        type=float,
        default=0.0,
        metavar="PERCENT",
        help="exit with status 1 if fewer glyphs than this are identical (default: never)",
    )
    parser.add_argument("--quiet", action="store_true", help="print only the total")


def run(args: argparse.Namespace) -> int:
    """Compare the fonts in two directories and report the share of identical glyphs."""
    fonts_a = font_files(args.dir_a, args.glob)
    fonts_b = font_files(args.dir_b, args.glob)
    names = sorted(set(fonts_a) & set(fonts_b))
    if not names:
        print("no fonts with the same name in both directories", file=sys.stderr)
        return 1
    totals = [0, 0]  # code points compared, identical
    for name in names:
        shared, same, only_a, only_b = compare(fonts_a[name], fonts_b[name])
        totals[0] += shared
        totals[1] += same
        if not args.quiet:
            print(
                f"{name:34} {shared:5} shared, {shared - same:4} differ "
                f"({percent(same, shared):6.2f}% identical)  only-A {only_a} only-B {only_b}"
            )
    overall = percent(totals[1], totals[0])
    unmatched = len(set(fonts_a) ^ set(fonts_b))
    print(
        f"TOTAL {len(names)} fonts, {totals[0]} code points compared, "
        f"{overall:.2f}% identical; fonts in only one directory: {unmatched}"
    )
    return 0 if overall >= args.min_identical else 1

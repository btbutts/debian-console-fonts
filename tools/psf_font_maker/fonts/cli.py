"""The ``fonts`` command: build the console fonts that were asked for."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.common.log import NORMAL, QUIET, VERBOSE, Heartbeat, set_level, step
from psf_font_maker.fonts.plan import Planner
from psf_font_maker.fonts.preflight import check_requirements
from psf_font_maker.fonts.report import Reporter, show_configuration, show_warnings
from psf_font_maker.fonts.runner import build_all
from psf_font_maker.fonts.selection import declare_selection, options_from

if TYPE_CHECKING:
    import argparse

NAME = "fonts"
HELP = "choose, convert and write console fonts (what `make fonts` runs)"


def declare(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of the command."""
    declare_selection(parser)
    parser.add_argument("--jobs", type=int, help="processes to use (default: one per CPU)")
    parser.add_argument(
        "--freetype-lib-dir",
        type=Path,
        help="directory holding the libfreetype to render TrueType fonts with; it must hold a "
        "usable one. Without it one is looked for and, failing that, built",
    )
    parser.add_argument(
        "--freetype-archive-dir",
        type=Path,
        action="append",
        default=[],
        help="a directory that may already hold the FreeType source archive (such as a package "
        "manager's download directory); it is used instead of downloading",
    )
    talk = parser.add_mutually_exclusive_group()
    talk.add_argument(
        "--quiet",
        action="store_true",
        help="say less while the fonts are made (a line per family and code set, and a "
        "heartbeat); the configuration, the checks of the environment, the stages and the "
        "warnings are always written",
    )
    talk.add_argument(
        "--verbose",
        action="store_true",
        help="say more while the fonts are made: each font written, every conversion warning",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--out", type=Path, help="write the fonts into this directory")
    target.add_argument("--list", action="store_true", help="only list the fonts")


def run(args: argparse.Namespace) -> int:
    """Carry out the command: say what was asked, check what it needs, then build."""
    set_level(QUIET if args.quiet else VERBOSE if args.verbose else NORMAL)
    options = options_from(args)
    if not args.list:
        show_configuration(options, args.out, args.jobs, args.freetype_lib_dir)
    planner = Planner(options)
    check_requirements(
        planner,
        lib_dirs=[args.freetype_lib_dir] if args.freetype_lib_dir else [],
        archive_dirs=args.freetype_archive_dir,
        jobs=args.jobs,
    )
    step("Planning: reading the face tables and working out which code sets each face covers")
    if args.list:
        names = planner.names()
        print("\n".join(names))
        print(f"{len(names)} fonts", file=sys.stderr)
        return 0
    jobs = planner.jobs()
    report = Reporter(options, jobs)
    report.show_plan(planner.selected())
    report.show_start(args.jobs)
    with Heartbeat(report.status):
        built = build_all(jobs, args.out, args.jobs, report.on_group)
    show_warnings(built)
    report.show_done(built, args.out)
    print(f"{len(built)} fonts in {args.out}/")
    return 0

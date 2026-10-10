"""The ``freetype`` command: find a FreeType that is new enough, or build one.

It runs before ``fonts`` (the Makefile does this) and prints the directory of the library
for ``fonts --freetype-lib-dir``. It prints nothing when no FreeType is needed or when the
system's loader finds one by itself.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from psf_font_maker.common.manifest import Manifest
from psf_font_maker.fonts.cli import declare_selection, options_from
from psf_font_maker.fonts.plan import Planner
from psf_font_maker.freetype_lib.build import PREFIX_DIR, SOURCE_NAME, build
from psf_font_maker.freetype_lib.errors import FreetypeError
from psf_font_maker.freetype_lib.locate import Located, explicit, locate, text
from psf_font_maker.otf2bdf.render import MINIMUM_FREETYPE

NAME = "freetype"
HELP = "find a FreeType that renders TrueType fonts correctly, or build one"


def declare(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of the command."""
    declare_selection(parser)
    parser.add_argument(
        "--lib-dir",
        type=Path,
        action="append",
        default=[],
        help="a directory holding the libfreetype to use (it must be new enough)",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        action="append",
        default=[],
        help="a directory that may already hold the FreeType source archive, such as the "
        "download directory of Buildroot; it is used instead of downloading",
    )
    parser.add_argument("--jobs", type=int, help="processes to build with")
    parser.add_argument("--no-build", action="store_true", help="never build, only look")
    parser.add_argument(
        "--clean", action="store_true", help="delete what was built (and downloaded) earlier"
    )
    parser.add_argument(
        "--always", action="store_true", help="provide FreeType even if no selected font needs it"
    )


def report(found: Located, how: str) -> int:
    """Say what is used on stderr and print its directory on stdout."""
    where = found.directory or "the system's library path"
    print(f"FreeType {text(found.version)} ({how}): {where}", file=sys.stderr)
    print(found.directory or "")
    return 0


def run(args: argparse.Namespace) -> int:
    """Carry out the command."""
    entry = Manifest(args.sources).entry(SOURCE_NAME)
    if args.clean:
        shutil.rmtree(entry.directory, ignore_errors=True)
        return 0
    if not args.always and not Planner(options_from(args)).needs_truetype():
        print("no selected font needs FreeType", file=sys.stderr)
        return 0
    if args.lib_dir:
        return report(explicit(args.lib_dir), "given")
    found, rejected = locate(entry.directory / PREFIX_DIR / "lib")
    if found is not None:
        return report(found, "found")
    wanted = text(MINIMUM_FREETYPE)
    print(f"no FreeType {wanted} or later found", file=sys.stderr)
    for line in rejected:
        print(f"  {line}", file=sys.stderr)
    if args.no_build:
        message = f"no FreeType {wanted} or later; run `make freetype` to build one"
        raise FreetypeError(message)
    directory = build(entry, args.jobs, args.archive_dir)
    return report(explicit([directory]), "built")

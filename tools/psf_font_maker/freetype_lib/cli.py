"""The ``freetype`` command: find a FreeType that is new enough, or build one.

It runs before ``fonts`` (the Makefile does this) and prints the directory of the library
for ``fonts --freetype-lib-dir``. It prints nothing when no FreeType is needed or when the
system's loader finds one by itself.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.common.log import detail, step
from psf_font_maker.common.manifest import Manifest
from psf_font_maker.fonts.plan import Planner
from psf_font_maker.fonts.selection import declare_selection, options_from
from psf_font_maker.freetype_lib.build import PREFIX_DIR, SOURCE_NAME, build
from psf_font_maker.freetype_lib.errors import FreetypeError
from psf_font_maker.freetype_lib.locate import Located, explicit, locate, text
from psf_font_maker.otf2bdf.render import MINIMUM_FREETYPE

if TYPE_CHECKING:
    from collections.abc import Sequence

    from psf_font_maker.common.manifest import SourceEntry

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


@dataclass(frozen=True)
class Chosen:
    """The FreeType that is used, and how it came to be chosen (given, found or built)."""

    located: Located
    how: str


def describe(chosen: Chosen) -> str:
    """Return one line that says which FreeType is used and where it is."""
    where = chosen.located.directory or "the system's library path"
    return f"FreeType {text(chosen.located.version)} ({chosen.how}): {where}"


@dataclass(frozen=True)
class Wish:
    """What the user said about FreeType: a directory to use, archives, jobs, no building."""

    lib_dirs: Sequence[Path] = ()
    archive_dirs: Sequence[Path] = ()
    jobs: int | None = None
    no_build: bool = False


def provide(entry: SourceEntry, wish: Wish, *, needed: bool) -> Chosen | None:
    """Choose the FreeType to use: the one named, one found, or one built; None if not needed.

    What is looked at, and what is found, is written on the log.
    """
    if not needed:
        detail("no selected font needs FreeType")
        return None
    if wish.lib_dirs:
        return Chosen(explicit(list(wish.lib_dirs)), "given")
    found, rejected = locate(entry.directory / PREFIX_DIR / "lib")
    if found is not None:
        return Chosen(found, "found")
    wanted = text(MINIMUM_FREETYPE)
    detail(f"no FreeType {wanted} or later found")
    for line in rejected:
        detail(line, 2)
    if wish.no_build:
        message = f"no FreeType {wanted} or later; run `make freetype` to build one"
        raise FreetypeError(message)
    detail("building one from FreeType's source (it needs a C compiler, make and, unless the")
    detail("archive is already at hand, the network)")
    directory = build(entry, wish.jobs, list(wish.archive_dirs))
    return Chosen(explicit([directory]), "built")


def run(args: argparse.Namespace) -> int:
    """Carry out the command."""
    entry = Manifest(args.sources).entry(SOURCE_NAME)
    if args.clean:
        shutil.rmtree(entry.directory, ignore_errors=True)
        return 0
    step("FreeType")
    needed = args.always or Planner(options_from(args)).wants_truetype()
    wish = Wish(args.lib_dir, args.archive_dir, args.jobs, no_build=args.no_build)
    chosen = provide(entry, wish, needed=needed)
    if chosen is None:
        return 0
    detail(describe(chosen))
    print(chosen.located.directory or "")
    return 0

"""The ``update-faces`` command."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from psf_font_maker.update_faces.faces import render

if TYPE_CHECKING:
    import argparse

NAME = "update-faces"
HELP = "regenerate mk/faces.mk from console-setup's Makefile"
DEBIAN_MAKEFILE = Path("sources/console-setup/Fonts/Makefile")
LOCK = Path("sources/sources.lock.json")
TARGET = Path("mk/faces.mk")


def declare(parser: argparse.ArgumentParser) -> None:
    """Declare the arguments of the command."""
    parser.add_argument("--check", action="store_true", help="fail if mk/faces.mk is stale")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(),
        help="the repository root that the paths are relative to (default: here)",
    )


def run(args: argparse.Namespace) -> int:
    """Rewrite mk/faces.mk, or with --check report whether it is current."""
    makefile, target = args.root / DEBIAN_MAKEFILE, args.root / TARGET
    if not makefile.is_file():
        print(f"error: {makefile} not found; run the downloader first", file=sys.stderr)
        return 1
    new = render(makefile, args.root / LOCK)
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != new:
            print("mk/faces.mk is out of date: run `make update-faces`", file=sys.stderr)
            return 1
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new, encoding="utf-8")
    print(f"wrote {TARGET} ({new.count(chr(10))} lines)")
    return 0

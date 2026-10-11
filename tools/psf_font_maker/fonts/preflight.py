"""Check, before anything is built, that what the selected fonts need is there.

Only DejaVu is drawn from TrueType files, with the freetype-py package and a FreeType of
version 2.13.3 or later. Everything that is looked at, and what was found, is written on the
log, so that a build that cannot work says so first and says what to fix.
"""

from __future__ import annotations

import platform
import sys
from typing import TYPE_CHECKING

from psf_font_maker.common.log import detail, step
from psf_font_maker.freetype_lib.binding import find as find_binding
from psf_font_maker.freetype_lib.cli import Wish, describe, provide
from psf_font_maker.freetype_lib.locate import text
from psf_font_maker.otf2bdf.render import MINIMUM_FREETYPE, load_freetype, use_library_dir

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from psf_font_maker.fonts.plan import Planner


def check_requirements(
    planner: Planner,
    *,
    lib_dirs: Sequence[Path] = (),
    archive_dirs: Sequence[Path] = (),
    jobs: int | None = None,
) -> None:
    """Write the requirements of the selection and check them; raise if one is not met.

    *lib_dirs* is a FreeType the user named (it is an error if it is not usable),
    *archive_dirs* may hold FreeType's source archive.
    """
    step("Requirements")
    detail(f"Python {platform.python_version()} ({sys.executable}); the tool needs 3.12 or later")
    if not planner.wants_truetype():
        detail("no selected face is drawn from a TrueType file: neither freetype-py nor FreeType")
        detail("is needed (only DejaVu is), so neither is looked for")
        return
    detail(
        f"a DejaVu face can be selected: it is drawn from TrueType files, which needs freetype-py "
        f"and FreeType {text(MINIMUM_FREETYPE)} or later"
    )
    find_binding()
    chosen = provide(
        planner.tree.manifest.entry("freetype"), Wish(lib_dirs, archive_dirs, jobs), needed=True
    )
    if chosen is not None:
        detail(describe(chosen))
        if chosen.located.directory is not None:
            use_library_dir(chosen.located.directory)
    module = load_freetype()
    version = ".".join(str(part) for part in module.version())
    name = getattr(getattr(module, "raw", None), "filename", None)
    detail(f"check: freetype-py loads FreeType {version}{f' from {name}' if name else ''}")

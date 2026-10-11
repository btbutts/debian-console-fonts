"""Find the freetype-py package (a Python module called ``freetype``) as an import would."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from psf_font_maker.common.log import detail
from psf_font_maker.freetype_lib.errors import FreetypeError
from psf_font_maker.freetype_lib.locate import text
from psf_font_maker.otf2bdf.library import library_files, probe_version

MODULE = "freetype"
DISTRIBUTION = "freetype-py"
MARKER = "__init__.py"
DEBIAN_PYTHON_DIR = "dist-packages"


@dataclass(frozen=True)
class Binding:
    """The freetype-py package that was found."""

    directory: Path
    version: str | None
    origin: str


def origin_of(directory: Path) -> str:
    """Say where in the Python installation the package is: a host tree, venv or system."""
    host = os.environ.get("HOST_DIR")
    if host and directory.is_relative_to(host):
        return f"the Buildroot host tree {host}"
    if sys.prefix != sys.base_prefix and directory.is_relative_to(sys.prefix):
        return f"the virtual environment {sys.prefix}"
    if DEBIAN_PYTHON_DIR in directory.parts:
        return "the system's Python packages (Debian/Ubuntu: apt install python3-freetype)"
    if directory.is_relative_to(sys.prefix):
        return f"the Python installation {sys.prefix} (Buildroot: its host package)"
    return "Python's import path"


def import_path() -> list[Path]:
    """Return the directories Python looks in for modules, the current one included."""
    return [Path(entry) if entry else Path.cwd() for entry in sys.path]


def find() -> Binding:
    """Look for freetype-py on the import path, writing each place on the log.

    It is not imported: importing it would already load a FreeType, and which one is for
    the caller to choose first.
    """
    detail(f"looking for freetype-py ({MODULE}) in the import path of {sys.executable}:")
    found: Path | None = None
    for base in import_path():
        candidate = base / MODULE
        if (candidate / MARKER).is_file():
            detail(f"{base}: found", 2)
            found = candidate
            break
        detail(f"{base}: not there", 2)
    if found is None:
        spec = importlib.util.find_spec(MODULE)
        if spec is not None and spec.origin:
            found = Path(spec.origin).parent
            detail(f"{found}: found by Python's import system", 2)
    if found is None:
        message = (
            "TrueType fonts (DejaVu) are drawn with the freetype-py package, which was not "
            f"found by {sys.executable}. Install it: pip install freetype-py in a virtual "
            "environment, apt install python3-freetype on Debian/Ubuntu, or, in Buildroot, "
            "depend on host-python-freetype-py"
        )
        raise FreetypeError(message)
    try:
        version = importlib.metadata.version(DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError:
        version = None
    binding = Binding(found, version, origin_of(found))
    detail(
        f"freetype-py {binding.version or '(version unknown)'} at {binding.directory}, "
        f"in {binding.origin}"
    )
    for library in library_files(found):
        bundled = probe_version(library)
        shown = text(bundled) if bundled else "not usable"
        detail(
            f"it carries its own FreeType, {library.name} ({shown}); whether that or the one "
            "chosen below is used is checked at the end",
            2,
        )
    return binding

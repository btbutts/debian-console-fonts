"""Tests for the Makefile: it passes your choices to the Python tool and nothing more.

The font logic itself is tested in test_fonts.py; these check the front door.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TERMINUS = ROOT / "data" / "fontsets" / "terminus-font"
FONT_DIR = Path("usr") / "share" / "consolefonts"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
needs_sources = pytest.mark.skipif(not TERMINUS.is_dir(), reason="fonts not downloaded")

# What a Buildroot configuration of Terminus, VGA, Unicode, Latin and Latin2 asks for.
BUILDROOT_FACES = "Terminus% VGA%"
BUILDROOT_CODESETS = "Uni1 Uni2 Uni3 Lat15 Lat2"
EXPECTED_PREFIXES = ("Terminus", "VGA")
EXPECTED_CODESETS = {"Uni1", "Uni2", "Uni3", "Lat15", "Lat2"}


def make(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run make quietly in *cwd*."""
    return subprocess.run(
        ["make", "-s", *args], cwd=cwd, capture_output=True, text=True, check=check
    )


def bare_checkout(tmp: Path) -> Path:
    """Copy only the Makefile, with no sources and no tools."""
    bare = tmp / "bare"
    bare.mkdir()
    shutil.copy(ROOT / "Makefile", bare / "Makefile")
    return bare


def test_help_and_clean_need_nothing_else(tmp_path: Path) -> None:
    """``make help`` and ``make clean`` work in a bare checkout."""
    bare = bare_checkout(tmp_path)
    assert "make install" in make("help", cwd=bare).stdout
    (bare / "out").mkdir()
    make("clean", cwd=bare)
    assert not (bare / "out").exists()


@needs_sources
def test_missing_sources_give_a_clear_error(tmp_path: Path) -> None:
    """A manifest whose paths lead to no fonts explains how to get the sources."""
    tables = tmp_path / "data"
    shutil.copytree(ROOT / "data", tables, ignore=shutil.ignore_patterns("fontsets"))
    manifest = shutil.copy(ROOT / "sources.json", tmp_path / "sources.json")
    result = make("list", f"DATA={tables}", f"SOURCES={manifest}", "FACES=Terminus16", check=False)
    assert result.returncode != 0
    assert "fetch the sources first" in result.stderr


@needs_sources
def test_list_passes_the_options_on() -> None:
    """FACES, CODESETS and SKIP reach the tool."""
    listed = make(
        "list", "FACES=TerminusBoldVGA%", "CODESETS=Uni2 Uni3", "SKIP=TerminusBoldVGA16"
    ).stdout.split()
    assert listed == ["Uni2-TerminusBoldVGA14", "Uni3-TerminusBoldVGA14"]


@needs_sources
def test_an_empty_selection_is_an_error_not_the_defaults() -> None:
    """``FACES=`` selects nothing, which is reported; it does not fall back to the defaults."""
    result = make("list", "FACES=", check=False)
    assert result.returncode != 0
    assert "select at least one" in result.stderr


@needs_sources
def test_install_writes_only_the_selected_fonts_under_destdir(tmp_path: Path) -> None:
    """The way a Buildroot package uses it: the configured fonts, in $(DESTDIR)$(FONTDIR)."""
    make(
        "install",
        f"DESTDIR={tmp_path}",
        f"FACES={BUILDROOT_FACES}",
        f"CODESETS={BUILDROOT_CODESETS}",
    )
    installed = sorted(path.name for path in (tmp_path / FONT_DIR).iterdir())
    assert installed
    assert all(name.endswith(".psf.gz") for name in installed)
    assert {name.split("-")[0] for name in installed} == EXPECTED_CODESETS
    assert all(name.split("-")[1].startswith(EXPECTED_PREFIXES) for name in installed)
    everything = sorted(path for path in tmp_path.rglob("*") if path.is_file())
    assert everything == sorted(tmp_path / FONT_DIR / name for name in installed)


@needs_sources
def test_install_honours_prefix_and_fontdir(tmp_path: Path) -> None:
    """PREFIX and FONTDIR decide where the fonts go."""
    make("install", f"DESTDIR={tmp_path}", "PREFIX=/opt/x", "FACES=Terminus16", "CODESETS=Uni2")
    assert (tmp_path / "opt" / "x" / "share" / "consolefonts" / "Uni2-Terminus16.psf.gz").is_file()
    make("install", f"DESTDIR={tmp_path}", "FONTDIR=/fonts", "FACES=Terminus16", "CODESETS=Uni2")
    assert (tmp_path / "fonts" / "Uni2-Terminus16.psf.gz").is_file()


@needs_sources
def test_fonts_builds_into_out(tmp_path: Path) -> None:
    """``make fonts OUT=...`` writes the fonts there."""
    make("fonts", f"OUT={tmp_path}", "FACES=Terminus20x10", "CODESETS=Uni2")
    assert [path.name for path in tmp_path.iterdir()] == ["Uni2-Terminus20x10.psf.gz"]


@needs_sources
def test_freetype_dir_must_hold_a_usable_library(tmp_path: Path) -> None:
    """A FREETYPE_LIB_DIR without a FreeType stops the build, before any font is made."""
    result = make(
        "fonts", f"OUT={tmp_path / 'out'}", f"FREETYPE_LIB_DIR={tmp_path}", "FACES=DejaVu%",
        check=False,
    )
    assert result.returncode != 0
    assert "not usable" in result.stderr
    assert not (tmp_path / "out").exists()


@needs_sources
def test_freetype_is_not_touched_for_bdf_fonts(tmp_path: Path) -> None:
    """Even a FREETYPE_LIB_DIR that is wrong is not looked at when no font needs FreeType."""
    make(
        "fonts", f"OUT={tmp_path}", "FREETYPE_LIB_DIR=/nonexistent", "FACES=Terminus20x10",
        "CODESETS=Uni2",
    )
    assert [path.name for path in tmp_path.iterdir()] == ["Uni2-Terminus20x10.psf.gz"]


def manifest_with_terminus_at(directory: Path, tmp: Path) -> Path:
    """Write a copy of sources.json that says Terminus is in *directory*; return its path."""
    manifest = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    manifest["terminus-font"]["destination-path"] = str(directory)  # absolute: taken as it is
    path = tmp / "sources.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@needs_sources
def test_the_manifest_decides_where_the_fonts_are(tmp_path: Path) -> None:
    """A source's ``dest`` in the manifest is where its fonts are looked for, nowhere else."""
    moved = tmp_path / "elsewhere"
    shutil.copytree(TERMINUS, moved)
    path = manifest_with_terminus_at(moved, tmp_path)
    listed = make("list", f"SOURCES={path}", "FACES=Terminus16", "CODESETS=Uni2").stdout
    assert listed.split() == ["Uni2-Terminus16"]
    empty = tmp_path / "empty"
    empty.mkdir()
    path = manifest_with_terminus_at(empty, tmp_path)
    result = make("list", f"SOURCES={path}", "FACES=Terminus16", check=False)
    assert result.returncode != 0
    assert "fetch the sources first" in result.stderr


def test_buildroot_downloads_reach_the_freetype_step() -> None:
    """FREETYPE_LIB_DIR and FREETYPE_ARCHIVE_DIR are passed on; unset, they are not."""
    plain = make("-n", "freetype").stdout
    assert "--archive-dir" not in plain
    assert "--lib-dir" not in plain
    passed = make(
        "-n", "freetype", "FREETYPE_ARCHIVE_DIR=/dl/pkg", "FREETYPE_LIB_DIR=/host/lib"
    ).stdout
    assert "--archive-dir '/dl/pkg'" in passed
    assert "--lib-dir '/host/lib'" in passed

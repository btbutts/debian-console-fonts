"""Tests for the checks made, and logged, before any font is built."""

from __future__ import annotations

import sys
from pathlib import Path
from time import sleep

import pytest
from support import needs_freetype

from psf_font_maker.common.log import LEVEL_ENV, NORMAL, Heartbeat, detail
from psf_font_maker.fonts import preflight
from psf_font_maker.fonts.options import Options
from psf_font_maker.fonts.plan import Planner
from psf_font_maker.freetype_lib import binding, locate
from psf_font_maker.freetype_lib.cli import Chosen
from psf_font_maker.freetype_lib.errors import FreetypeError
from psf_font_maker.freetype_lib.locate import Located
from psf_font_maker.main import main

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCES = ROOT / "sources.json"
FAKE_VERSION = (2, 14, 3)
LIBRARY_NAME = "libfreetype.dylib" if sys.platform == "darwin" else "libfreetype.so"
needs_fonts = pytest.mark.skipif(
    not (DATA / "fontsets" / "terminus-font").is_dir(), reason="fonts not downloaded"
)


def fake_package(base: Path) -> Path:
    """Make a directory that looks like an installed ``freetype`` package; return it."""
    package = base / binding.MODULE
    package.mkdir(parents=True)
    (package / binding.MARKER).write_text("", encoding="utf-8")
    return package


def test_every_place_looked_at_for_freetype_py_is_logged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The import path is walked in order, each entry is reported, and the hit is named."""
    empty, site = tmp_path / "first", tmp_path / "site"
    empty.mkdir()
    package = fake_package(site)
    monkeypatch.setattr(sys, "path", [str(empty), str(site), str(tmp_path / "never")])
    found = binding.find()
    err = capsys.readouterr().err
    assert found.directory == package
    assert f"{empty}: not there" in err
    assert f"{site}: found" in err
    assert "never" not in err  # the search stops at the first hit, like an import


def test_missing_freetype_py_says_how_to_get_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With the package nowhere on the path the error names the three ways to install it."""
    monkeypatch.setattr(sys, "path", [str(tmp_path)])
    monkeypatch.setattr(binding.importlib.util, "find_spec", lambda _name: None)
    with pytest.raises(FreetypeError, match="pip install freetype-py") as caught:
        binding.find()
    assert "python3-freetype" in str(caught.value)
    assert "host-python-freetype-py" in str(caught.value)


def test_where_the_package_lives_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Buildroot host tree, a virtual environment and a Debian package are told apart."""
    monkeypatch.setenv("HOST_DIR", "/br/host")
    assert "Buildroot host tree /br/host" in binding.origin_of(
        Path("/br/host/lib/python3.12/site-packages/freetype")
    )
    monkeypatch.delenv("HOST_DIR")
    monkeypatch.setattr(sys, "prefix", "/home/me/venv")
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    assert "virtual environment" in binding.origin_of(
        Path("/home/me/venv/lib/python3.12/site-packages/freetype")
    )
    assert "python3-freetype" in binding.origin_of(Path("/usr/lib/python3/dist-packages/freetype"))


@needs_fonts
def test_nothing_is_looked_for_when_no_face_needs_truetype(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A BDF-only selection says so, and neither freetype-py nor FreeType is touched."""

    def fail() -> None:
        pytest.fail("looked for freetype-py")

    monkeypatch.setattr(preflight, "find_binding", fail)
    planner = Planner(Options(data=DATA, sources=SOURCES, faces=("Terminus16",)))
    preflight.check_requirements(planner)
    err = capsys.readouterr().err
    assert "==> Requirements" in err
    assert "neither freetype-py nor FreeType" in err


@needs_fonts
@needs_freetype
def test_requirements_are_checked_in_order_and_before_planning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Configuration, then requirements (freetype-py, then FreeType), then the plan."""

    def looking() -> binding.Binding:
        detail("looking for freetype-py")
        return binding.Binding(tmp_path, "2.5.1", "a test")

    def chosen(*_args: object, **_kwargs: object) -> Chosen:
        return Chosen(Located(tmp_path, FAKE_VERSION), "given")

    monkeypatch.setattr(preflight, "find_binding", looking)
    monkeypatch.setattr(preflight, "provide", chosen)
    monkeypatch.setattr(preflight, "use_library_dir", lambda _directory: None)
    arguments = ["fonts", "--data", str(DATA), "--sources", str(SOURCES)]
    arguments += ["--faces", "DejaVu30x16", "--codesets", "Uni2", "--list"]
    assert main(arguments) == 0
    err = capsys.readouterr().err
    order = ["==> Requirements", "looking for freetype-py", "FreeType 2.14.3 (given)"]
    order += ["check: freetype-py loads", "==> Planning"]
    positions = [err.index(text) for text in order]
    assert positions == sorted(positions)


@needs_fonts
def test_configuration_comes_first_and_quiet_keeps_the_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first thing written is what was asked for; --quiet does not take it away."""
    monkeypatch.setenv(LEVEL_ENV, str(NORMAL))  # restored afterwards, whatever the command sets
    arguments = ["fonts", "--data", str(DATA), "--sources", str(SOURCES), "--jobs", "1"]
    arguments += ["--faces", "Fixed13", "--codesets", "Uni2", "--out", str(tmp_path / "out")]
    assert main(arguments) == 0
    err = capsys.readouterr().err
    assert err.startswith("==> Configuration")
    assert err.index("==> Configuration") < err.index("==> Requirements")
    assert main([*arguments[:-1], str(tmp_path / "out2"), "--quiet"]) == 0
    quiet = capsys.readouterr().err
    assert quiet.startswith("==> Configuration")
    assert "==> Requirements" in quiet


def test_each_library_is_tested_and_the_verdict_is_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The path of each library and its version are written, with PASS or TOO OLD."""
    old, new = tmp_path / "old", tmp_path / "new"
    names = {}
    for directory in (old, new):
        directory.mkdir()
        library = directory / LIBRARY_NAME
        library.write_text("x", encoding="utf-8")
        names[library] = (2, 12, 1) if directory == old else (2, 14, 3)
    monkeypatch.setattr(locate, "probe_version", lambda library: names[Path(library)])
    found = locate.search([old, new], [])
    err = capsys.readouterr().err
    assert found is not None
    assert found.directory == new
    assert "FreeType version 2.12.1 (need 2.13.3 or later): TOO OLD" in err
    assert "FreeType version 2.14.3 (need 2.13.3 or later): PASS" in err
    assert err.index("TOO OLD") < err.index("PASS")
    assert str(found.library) in err


def test_a_quiet_stretch_gets_a_heartbeat(capsys: pytest.CaptureFixture[str]) -> None:
    """While nothing else is written, the status is repeated now and then."""
    with Heartbeat(lambda: "still building", interval=0.0):
        sleep(1.5)
    assert "... still building" in capsys.readouterr().err

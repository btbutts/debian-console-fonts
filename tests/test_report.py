"""Tests for the messages the ``fonts`` command writes while it builds."""

from __future__ import annotations

from pathlib import Path

import pytest

from psf_font_maker.common.log import LEVEL_ENV, NORMAL, QUIET, VERBOSE
from psf_font_maker.fonts.options import Options
from psf_font_maker.fonts.plan import FontJob
from psf_font_maker.fonts.report import (
    Reporter,
    codeset_of,
    family_of,
    kind_of,
    show_configuration,
    show_warnings,
)
from psf_font_maker.fonts.runner import Built, Group

OUT = Path("out")
FACES = ("Terminus%", "Fixed%")


def job(codeset: str, face: str) -> FontJob:
    """Return a job that only has a name; nothing here builds it."""
    return FontJob(f"{codeset}-{face}", face, (), (), (), 256, framebuffer=False)


def plan() -> list[FontJob]:
    """Return two Terminus faces and one Fixed face, for two code sets each."""
    return [
        job(codeset, face)
        for face in ("Terminus16", "Terminus20x10", "Fixed13")
        for codeset in ("Uni1", "Uni2")
    ]


def group(face: str, *, warnings: tuple[str, ...] = ()) -> Group:
    """Return the result of building *face* for both code sets."""
    built = [Built(f"{codeset}-{face}", list(warnings)) for codeset in ("Uni1", "Uni2")]
    return Group(face, built, 0.5)


def test_family_is_the_pattern_that_selected_the_face() -> None:
    """A family is named after its face pattern, without the wildcard."""
    assert family_of("TerminusBold16", FACES) == "Terminus"
    assert family_of("Fixed13", FACES) == "Fixed"
    assert family_of("Other", FACES) == "Other"
    assert codeset_of("Uni2-TerminusBold16") == "Uni2"


def test_warning_kinds_ignore_code_points_and_numbers() -> None:
    """Warnings that differ only in a code point or a count are one kind."""
    first = kind_of("U+2591: 8 broken pixel(s)\n")
    assert first == kind_of("U+00C4: 2 broken pixel(s)")
    assert first != kind_of("U+00C4: no glyph defined")


def test_configuration_names_every_option(capsys: pytest.CaptureFixture[str]) -> None:
    """What was asked for is written before anything is done."""
    options = Options(faces=("Terminus%",), codesets=("Uni1", "Lat15"), skip=("TerminusBold16",))
    show_configuration(options, OUT, 3, Path("/host/lib"))
    err = capsys.readouterr().err
    for text in ("Terminus%", "Uni1 Lat15", "TerminusBold16", "/host/lib", "processes     : 3"):
        assert text in err


def test_plan_counts_fonts_per_family_and_code_set(capsys: pytest.CaptureFixture[str]) -> None:
    """The plan gives faces, fonts and fonts per code set for each family."""
    options = Options(faces=FACES, codesets=("Uni1", "Uni2"))
    Reporter(options, plan()).show_plan(["Terminus16", "Terminus20x10", "Fixed13"])
    err = capsys.readouterr().err
    assert "Plan: 6 fonts from 3 faces" in err
    assert "Terminus : 2 faces, 4 fonts (Uni1 2  Uni2 2)" in err
    assert "WARNING" not in err


def test_requests_that_select_nothing_are_warned_about(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A face pattern or code set that gives no font is reported."""
    options = Options(faces=(*FACES, "Missing%"), codesets=("Uni1", "Bogus"))
    Reporter(options, plan()).show_plan(["Terminus16", "Terminus20x10", "Fixed13"])
    err = capsys.readouterr().err
    assert "face pattern Missing%" in err
    assert "code set Bogus" in err
    assert "code set Uni1" not in err


@pytest.fixture(autouse=True)
def normal_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test at the default level of detail (a command may have changed it)."""
    monkeypatch.setenv(LEVEL_ENV, str(NORMAL))


def test_progress_reports_each_face_family_and_code_set(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each face, each family and code set when complete, and the running percentage."""
    reporter = Reporter(Options(faces=FACES), plan())
    reporter.on_group(group("Terminus16"))
    first = capsys.readouterr().err
    assert "Terminus16: 2 fonts (Uni1 Uni2) in 0.5s" in first
    assert "all done" not in first
    reporter.on_group(group("Terminus20x10"))
    reporter.on_group(group("Fixed13", warnings=("U+0041: no glyph defined\n",)))
    err = capsys.readouterr().err
    assert "Terminus Uni1: 2/2 fonts done (all: 4/6, 66%" in err
    assert "Fixed Uni2: 1/1 fonts done (all: 6/6, 100%" in err
    assert "Terminus: all done, 4 fonts in 2 faces (Uni1 2  Uni2 2)" in err
    assert "Fixed: all done, 2 fonts in 1 faces (Uni1 1  Uni2 1), 0.5s of work, 2 warnings" in err
    assert "progress: 4/6 fonts (66%)" in err


def test_quiet_still_reports_each_family_and_code_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """At the quiet level the stages and every family and code set remain; faces go."""
    monkeypatch.setenv(LEVEL_ENV, str(QUIET))
    reporter = Reporter(Options(faces=FACES), plan())
    reporter.show_plan(["Terminus16", "Terminus20x10", "Fixed13"])
    reporter.show_start(2)
    for face in ("Terminus16", "Terminus20x10", "Fixed13"):
        reporter.on_group(group(face))
    built = [Built("Uni1-Fixed13", ["U+0041: no glyph defined\n"])]
    show_warnings(built)
    reporter.show_done(built, OUT)
    err = capsys.readouterr().err
    for text in ("==> Plan: 6 fonts", "==> Building 6 fonts", "==> Done: 1 fonts"):
        assert text in err
    assert "Terminus Uni1: 2/2 fonts done" in err
    assert "Terminus Uni2: 2/2 fonts done" in err
    assert "Fixed Uni1: 1/1 fonts done" in err
    assert "1 conversion warnings in 1 of 1 fonts" in err
    assert "Terminus16:" not in err  # the faces are for the normal level
    assert "progress:" not in err


def test_the_status_line_says_how_far_the_build_is() -> None:
    """The heartbeat's sentence has the counts and the elapsed time."""
    reporter = Reporter(Options(faces=FACES), plan())
    reporter.on_group(group("Fixed13"))
    assert reporter.status().startswith("building: 2/6 fonts (33%), 1 faces done, ")


def test_warnings_are_summarised_or_listed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """By default the kinds of warning are counted; at the verbose level every one is listed."""
    built = [
        Built("Uni1-Fixed13", ["U+0041: no glyph defined\n", "U+0042: no glyph defined\n"]),
        Built("Uni2-Fixed13", ["U+2591: 8 broken pixel(s)\n"]),
        Built("Uni2-Fixed14", []),
    ]
    show_warnings(built)
    summary = capsys.readouterr().err
    assert "3 conversion warnings in 2 of 3 fonts" in summary
    assert "2 x U+XXXX: no glyph defined   e.g. Uni1-Fixed13: U+0041" in summary
    assert "U+0042" not in summary
    monkeypatch.setenv(LEVEL_ENV, str(VERBOSE))
    show_warnings(built)
    listing = capsys.readouterr().err
    assert "WARNING: Uni1-Fixed13: U+0042: no glyph defined" in listing
    assert "WARNING: Uni2-Fixed13: U+2591: 8 broken pixel(s)" in listing

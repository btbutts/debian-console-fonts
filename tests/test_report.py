"""Tests for the messages the ``fonts`` command writes while it builds."""

from __future__ import annotations

from pathlib import Path

import pytest

from psf_font_maker.fonts.options import Options
from psf_font_maker.fonts.plan import FontJob
from psf_font_maker.fonts.report import (
    Reporter,
    codeset_of,
    family_of,
    kind_of,
    show_configuration,
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


def test_progress_reports_each_finished_family(capsys: pytest.CaptureFixture[str]) -> None:
    """A family is reported when all its faces are done, with its fonts per code set."""
    reporter = Reporter(Options(faces=FACES), plan())
    reporter.on_group(group("Terminus16"))
    assert "finished" not in capsys.readouterr().err
    reporter.on_group(group("Terminus20x10"))
    reporter.on_group(group("Fixed13", warnings=("U+0041: no glyph defined\n",)))
    err = capsys.readouterr().err
    assert "Terminus: finished, 4 fonts in 2 faces (Uni1 2  Uni2 2)" in err
    assert "Fixed: finished, 2 fonts in 1 faces (Uni1 1  Uni2 1), 0.5s of work, 2 warnings" in err
    assert "progress: 4/6 fonts (66%)" in err


def test_quiet_writes_no_progress_but_still_warns(capsys: pytest.CaptureFixture[str]) -> None:
    """With --quiet only warnings remain."""
    reporter = Reporter(Options(faces=FACES), plan(), quiet=True)
    for face in ("Terminus16", "Terminus20x10", "Fixed13"):
        reporter.on_group(group(face))
    built = [Built("Uni1-Fixed13", ["U+0041: no glyph defined\n"])]
    reporter.show_warnings(built)
    reporter.show_done(built, OUT)
    err = capsys.readouterr().err
    assert "==>" not in err
    assert "progress" not in err
    assert "1 conversion warnings in 1 of 1 fonts" in err


def test_warnings_are_summarised_or_listed(capsys: pytest.CaptureFixture[str]) -> None:
    """By default the kinds of warning are counted; --verbose lists every one."""
    built = [
        Built("Uni1-Fixed13", ["U+0041: no glyph defined\n", "U+0042: no glyph defined\n"]),
        Built("Uni2-Fixed13", ["U+2591: 8 broken pixel(s)\n"]),
        Built("Uni2-Fixed14", []),
    ]
    Reporter(Options(faces=FACES), plan()).show_warnings(built)
    summary = capsys.readouterr().err
    assert "3 conversion warnings in 2 of 3 fonts" in summary
    assert "2 x U+XXXX: no glyph defined   e.g. Uni1-Fixed13: U+0041" in summary
    assert "U+0042" not in summary
    Reporter(Options(faces=FACES), plan(), verbose=True).show_warnings(built)
    listing = capsys.readouterr().err
    assert "WARNING: Uni1-Fixed13: U+0042: no glyph defined" in listing
    assert "WARNING: Uni2-Fixed13: U+2591: 8 broken pixel(s)" in listing

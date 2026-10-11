"""Tell the person running a build what was asked for, how far it is and how it ended.

Everything is written on standard error (see ``common.log``). Progress is reported for sets
of fonts, not for single files: a *family* is what one requested face pattern selected
(``Terminus%`` gives ``Terminus``), and its fonts are counted per code set.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING

from psf_font_maker.common.log import QUIET, VERBOSE, detail, emit, level, note, step, warn
from psf_font_maker.fonts.patterns import matches
from psf_font_maker.fonts.runner import worker_count

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from psf_font_maker.fonts.options import Options
    from psf_font_maker.fonts.plan import FontJob
    from psf_font_maker.fonts.runner import Built, Group

PERCENT_STEP = 10
UNICODE_REFERENCE = re.compile(r"U\+[0-9A-Fa-f]+")
NUMBER = re.compile(r"\d+")
KINDS_SHOWN = 8


def family_of(face: str, patterns: Sequence[str]) -> str:
    """Return the name of the requested pattern that selected *face* (``Terminus%`` -> Terminus)."""
    for pattern in patterns:
        if matches(pattern, face):
            return pattern.replace("%", "") or face
    return face


def codeset_of(name: str) -> str:
    """Return the code set of a font name (``Uni2-TerminusBold16`` -> Uni2)."""
    return name.partition("-")[0]


def kind_of(message: str) -> str:
    """Return a warning's wording with the code point and the numbers left out."""
    return NUMBER.sub("N", UNICODE_REFERENCE.sub("U+XXXX", message.strip()))


def words(values: Sequence[str]) -> str:
    """Return *values* as one line of text, or ``(none)``."""
    return " ".join(values) or "(none)"


def show_configuration(
    options: Options, out: Path, workers: int | None, freetype: Path | None
) -> None:
    """Say what the tool was given (the options, after the Makefile's and the defaults')."""
    step("Configuration")
    detail(f"face patterns : {words(options.faces)}")
    detail(f"code sets     : {words(options.codesets)}")
    detail(f"skipped faces : {words(options.skip)}")
    detail(f"face pool     : {options.pool}")
    detail(
        f"DejaVu        : cell widths {words([str(size) for size in options.dejavu.sizes])}, "
        f"proportional faces {'on' if options.dejavu.proportional else 'off'}"
    )
    detail(f"data          : {options.data}")
    detail(f"sources       : {options.sources}")
    detail(f"FreeType      : {freetype or 'whatever the system finds (or none needed)'}")
    detail(f"processes     : {workers or 'one per CPU'}")
    detail(f"output        : {out}")


def show_warnings(built: Sequence[Built]) -> None:
    """Report the warnings the conversions gave: all of them, or a summary of the kinds."""
    flagged = [item for item in built if item.warnings]
    total = sum(len(item.warnings) for item in flagged)
    if not total:
        return
    if level() >= VERBOSE:
        for item in flagged:
            for message in item.warnings:
                warn(f"{item.name}: {message.strip()}")
        return
    warn(f"{total} conversion warnings in {len(flagged)} of {len(built)} fonts (by kind):")
    kinds: Counter[str] = Counter()
    example: dict[str, tuple[str, str]] = {}
    for item in flagged:
        for message in item.warnings:
            kind = kind_of(message)
            kinds[kind] += 1
            example.setdefault(kind, (item.name, message.strip()))
    for kind, count in kinds.most_common(KINDS_SHOWN):
        name, message = example[kind]
        emit(f"    {count:6d} x {kind}   e.g. {name}: {message}")
    if len(kinds) > KINDS_SHOWN:
        emit(f"    ... and {len(kinds) - KINDS_SHOWN} more kinds")
    emit("    (--verbose, or VERBOSE=1 with make, lists every warning)")


@dataclass
class Family:
    """The fonts one face pattern selected, and how far their building is."""

    name: str
    faces: set[str] = field(default_factory=set)
    codesets: Counter[str] = field(default_factory=Counter)
    fonts_done: int = 0
    warnings: int = 0
    seconds: float = 0.0

    @property
    def fonts(self) -> int:
        """The number of fonts of the family."""
        return sum(self.codesets.values())

    def counts(self) -> str:
        """Return the fonts per code set (``Uni1 38  Uni2 38``)."""
        return "  ".join(f"{name} {count}" for name, count in sorted(self.codesets.items()))


@dataclass
class Tally:
    """How much of the whole is done."""

    faces: int = 0
    fonts: int = 0
    next_percent: int = PERCENT_STEP
    started: float = field(default_factory=monotonic)


class Reporter:
    """Reports on one run of the ``fonts`` command.

    How much is said while the fonts are made is the level of the log module: a line for
    each family and code set that is done at all levels, each face and the running
    percentage from ``NORMAL`` on, and every conversion warning at ``VERBOSE``.
    """

    def __init__(
        self,
        options: Options,
        jobs: Sequence[FontJob],
    ) -> None:
        """Group the fonts of the plan into families."""
        self.options = options
        self.jobs = jobs
        self.codeset_total: Counter[tuple[str, str]] = Counter()
        self.codeset_done: Counter[tuple[str, str]] = Counter()
        self.families: dict[str, Family] = {}
        self.family_of_face: dict[str, str] = {}
        for job in jobs:
            name = family_of(job.face, options.faces)
            family = self.families.setdefault(name, Family(name))
            family.faces.add(job.face)
            family.codesets[codeset_of(job.name)] += 1
            self.codeset_total[name, codeset_of(job.name)] += 1
            self.family_of_face[job.face] = name
        self.tally = Tally()

    # --- what was asked ----------------------------------------------------------

    def show_plan(self, faces_selected: Sequence[str]) -> None:
        """Say which fonts the options came to, and warn about requests that gave nothing."""
        fonts = len(self.jobs)
        faces = len({job.face for job in self.jobs})
        step(f"Plan: {fonts} fonts from {faces} faces")
        width = max((len(name) for name in self.families), default=0)
        for family in sorted(self.families.values(), key=lambda item: item.name):
            detail(
                f"{family.name:<{width}} : {len(family.faces)} faces, "
                f"{family.fonts} fonts ({family.counts()})"
            )
        for pattern in self.options.faces:
            if not any(matches(pattern, face) for face in faces_selected):
                warn(f"face pattern {pattern}: no face of the pool fits it")
        built_sets = {codeset_of(job.name) for job in self.jobs}
        for pattern in self.options.codesets:
            if not any(matches(pattern, codeset) for codeset in built_sets):
                warn(f"code set {pattern}: no selected face covers it, so no font is made for it")

    def show_start(self, workers: int | None) -> None:
        """Say that the conversion starts."""
        faces = len({job.face for job in self.jobs})
        count = worker_count(workers, faces)
        step(f"Building {len(self.jobs)} fonts with {count} process{'es' if count != 1 else ''}")
        detail("each face is converted for all of its code sets, then compressed and written")

    # --- how it goes -------------------------------------------------------------

    def status(self) -> str:
        """Return a sentence on how far the build is (for the heartbeat)."""
        tally = self.tally
        total = len(self.jobs)
        percent = 100 * tally.fonts // total if total else 100
        return (
            f"building: {tally.fonts}/{total} fonts ({percent}%), {tally.faces} faces done, "
            f"{monotonic() - tally.started:.0f}s elapsed"
        )

    def on_group(self, group: Group) -> None:
        """Count a finished face and say what that completed, at the level asked for."""
        family = self.families[self.family_of_face[group.face]]
        fonts = len(group.built)
        warnings = sum(len(built.warnings) for built in group.built)
        family.fonts_done += fonts
        family.seconds += group.seconds
        family.warnings += warnings
        tally = self.tally
        tally.faces += 1
        tally.fonts += fonts
        sets = Counter(codeset_of(built.name) for built in group.built)
        flagged = f", {warnings} warnings" if warnings else ""
        names = " ".join(sorted(sets))
        note(f"{group.face}: {fonts} fonts ({names}) in {group.seconds:.1f}s{flagged}")
        total = len(self.jobs)
        percent = 100 * tally.fonts // total
        for codeset, count in sets.items():
            key = (family.name, codeset)
            self.codeset_done[key] += count
            if self.codeset_done[key] == self.codeset_total[key]:
                note(
                    f"{family.name} {codeset}: {self.codeset_done[key]}/"
                    f"{self.codeset_total[key]} fonts done (all: {tally.fonts}/{total}, "
                    f"{percent}%, {monotonic() - tally.started:.0f}s)",
                    at=QUIET,
                )
        if family.fonts_done == family.fonts:
            extra = f", {family.warnings} warnings" if family.warnings else ""
            note(
                f"{family.name}: all done, {family.fonts} fonts in {len(family.faces)} faces "
                f"({family.counts()}), {family.seconds:.1f}s of work{extra}"
            )
        if percent >= tally.next_percent and tally.fonts < total:
            tally.next_percent = (percent // PERCENT_STEP + 1) * PERCENT_STEP
            note(
                f"progress: {tally.fonts}/{total} fonts ({percent}%), "
                f"{tally.faces} faces done, {monotonic() - tally.started:.1f}s"
            )

    # --- how it ended ------------------------------------------------------------

    def show_done(self, built: Sequence[Built], out: Path) -> None:
        """Say that the work is finished and how long it took."""
        warnings = sum(len(item.warnings) for item in built)
        step(
            f"Done: {len(built)} fonts in {out}/ in {monotonic() - self.tally.started:.1f}s"
            f"{f', {warnings} warnings' if warnings else ''}"
        )

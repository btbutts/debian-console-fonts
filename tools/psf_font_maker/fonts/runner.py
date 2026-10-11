"""Build the fonts of a plan: convert, compress and write them, in parallel."""

from __future__ import annotations

import gzip
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

from psf_font_maker.bdf2psf import output
from psf_font_maker.bdf2psf.classify import FRAMEBUFFER, TEXT_MODE
from psf_font_maker.bdf2psf.convert import Request, build
from psf_font_maker.common.errors import ToolError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from psf_font_maker.fonts.plan import FontJob

COMPRESSION_LEVEL = 9
SUFFIX = ".psf.gz"


class BuildError(ToolError):
    """A font could not be built."""


@dataclass
class Built:
    """A font that was written, and the warnings its conversion gave."""

    name: str
    warnings: list[str]


@dataclass
class Group:
    """The fonts of one face, which one process builds, and the time that took."""

    face: str
    built: list[Built]
    seconds: float


def compress(data: bytes) -> bytes:
    """Return *data* gzip-compressed the reproducible way (maximum level, no timestamp)."""
    return gzip.compress(data, compresslevel=COMPRESSION_LEVEL, mtime=0)


def convert(job: FontJob) -> tuple[bytes, list[str]]:
    """Convert one font; return its PSF bytes and the warnings."""
    request = Request(
        bdfs=[spec.load() for spec in job.bdfs],
        equivalents=list(job.equivalents),
        symbols=list(job.symbols),
        font_size=job.size,
        font_type=FRAMEBUFFER if job.framebuffer else TEXT_MODE,
        echo=False,
    )
    return output.encode(build(request)), request.warnings


def write_font(job: FontJob, out: Path) -> Built:
    """Build one font and write ``<name>.psf.gz`` into the directory *out*."""
    try:
        data, warnings = convert(job)
    except (ToolError, OSError) as exc:
        message = f"{job.name}: {exc}"
        raise BuildError(message) from exc
    target = out / f"{job.name}{SUFFIX}"
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(compress(data))
    partial.replace(target)
    return Built(job.name, warnings)


def write_group(args: tuple[Sequence[FontJob], Path]) -> Group:
    """Build the fonts of one face one after another (they share rendered fonts)."""
    jobs, out = args
    started = monotonic()
    built = [write_font(job, out) for job in jobs]
    return Group(jobs[0].face, built, monotonic() - started)


def by_face(jobs: Sequence[FontJob]) -> list[list[FontJob]]:
    """Group the jobs by face, so that a face rendered once serves every code set."""
    ordered = sorted(jobs, key=lambda job: job.face)
    return [list(group) for _, group in groupby(ordered, key=lambda job: job.face)]


def worker_count(workers: int | None, groups: int) -> int:
    """Return how many processes to use: *workers* (default: one per CPU), at most one a group."""
    return max(1, min(workers or os.cpu_count() or 1, groups))


def build_all(
    jobs: Sequence[FontJob],
    out: Path,
    workers: int | None = None,
    on_group: Callable[[Group], None] | None = None,
) -> list[Built]:
    """Build every font into *out*; use *workers* processes (default: one per CPU).

    *on_group* is called, here and not in a worker, as each face is finished.
    """
    out.mkdir(parents=True, exist_ok=True)
    groups = by_face(jobs)
    results: list[Group] = []

    def finished(group: Group) -> None:
        results.append(group)
        if on_group is not None:
            on_group(group)

    count = worker_count(workers, len(groups))
    if count == 1:
        for group in groups:
            finished(write_group((group, out)))
    else:
        with ProcessPoolExecutor(max_workers=count) as pool:
            pending = [pool.submit(write_group, (group, out)) for group in groups]
            for future in as_completed(pending):
                finished(future.result())
    return sorted(
        (built for group in results for built in group.built), key=lambda built: built.name
    )

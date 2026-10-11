"""Messages for the person running the tool: one line each, on stderr, written at once.

Standard output is left to results (a list of fonts, a directory a caller captures), so
everything here goes to standard error. Each line is flushed so that it shows up in a
build log as it happens, also when the line comes from a worker process.

There are three levels of detail. They only decide how much is said *while the fonts are
being made*; what was asked for, every check of the build environment, every stage and the
warnings are written at all of them, because that is what is needed to find out why a build
does not work.

* ``QUIET``: one line when a family of fonts has finished a code set, and a line now and then
  while nothing else is said, so that a long build is never silent.
* ``NORMAL``: also each face as it is finished, each TrueType font as it is rendered and the
  running percentage.
* ``VERBOSE``: also each font as it is written, and every conversion warning.

The level is kept in the environment so that worker processes, which start afresh, share it.
"""

from __future__ import annotations

import os
import sys
import threading
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

INDENT = "    "
QUIET, NORMAL, VERBOSE = 0, 1, 2
LEVEL_ENV = "PSF_FONT_MAKER_LOG_LEVEL"
HEARTBEAT_SECONDS = 10.0
CHECK_SECONDS = 1.0


class Clock:
    """When the last line was written, for the heartbeat."""

    def __init__(self) -> None:
        """Start the clock now."""
        self._last_line = monotonic()

    def touch(self) -> None:
        """Note that a line was just written."""
        self._last_line = monotonic()

    def silent_for(self) -> float:
        """Return the seconds since the last line."""
        return monotonic() - self._last_line


CLOCK = Clock()


def set_level(level_number: int) -> None:
    """Set how much is said while fonts are made (from here on, here and in workers)."""
    os.environ[LEVEL_ENV] = str(level_number)


def level() -> int:
    """Return the level of detail: ``QUIET``, ``NORMAL`` or ``VERBOSE``."""
    try:
        return int(os.environ.get(LEVEL_ENV, NORMAL))
    except ValueError:
        return NORMAL


def emit(message: str) -> None:
    """Write *message* as one line on standard error."""
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()
    CLOCK.touch()


def step(message: str) -> None:
    """Write the heading of a step of the work."""
    emit(f"==> {message}")


def detail(message: str, depth: int = 1) -> None:
    """Write a line that belongs to the step above, indented *depth* levels."""
    emit(f"{INDENT * depth}{message}")


def note(message: str, depth: int = 1, *, at: int = NORMAL) -> None:
    """Write a line about the work in progress, if the level of detail is *at* or more."""
    if level() >= at:
        detail(message, depth)


def warn(message: str) -> None:
    """Write a warning."""
    emit(f"WARNING: {message}")


class Heartbeat:
    """Writes a line saying what is going on whenever nothing else was written for a while.

    Used around work that can take long without anything to report, so that a log is not
    silent while the machine is busy. It is a context manager.
    """

    def __init__(self, status: Callable[[], str], interval: float = HEARTBEAT_SECONDS) -> None:
        """Say ``status()`` after *interval* seconds of silence, again and again."""
        self._status = status
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        """Check now and then whether the log has been silent too long."""
        while not self._stop.wait(CHECK_SECONDS):
            if CLOCK.silent_for() >= self._interval:
                detail(f"... {self._status()}")

    def __enter__(self) -> Heartbeat:
        """Start watching."""
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop watching."""
        self._stop.set()
        self._thread.join()

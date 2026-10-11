"""Messages for the person running the tool: one line each, on stderr, written at once.

Standard output is left to results (a list of fonts, a directory a caller captures), so
everything here goes to standard error. Each line is flushed so that it shows up in a
build log as it happens, also when the line comes from a worker process.

Quiet is kept in the environment so that worker processes, which start afresh, share it:
progress and detail lines are then left out, and warnings are still written.
"""

from __future__ import annotations

import os
import sys

INDENT = "    "
QUIET_ENV = "PSF_FONT_MAKER_QUIET"


def set_quiet(*, quiet: bool) -> None:
    """Leave out progress and detail lines (from here on, in this process and its workers)."""
    if quiet:
        os.environ[QUIET_ENV] = "1"
    else:
        os.environ.pop(QUIET_ENV, None)


def is_quiet() -> bool:
    """Return True if only warnings are to be written."""
    return bool(os.environ.get(QUIET_ENV))


def emit(message: str) -> None:
    """Write *message* as one line on standard error."""
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()


def say(message: str) -> None:
    """Write *message* as one line on standard error, unless quiet."""
    if not is_quiet():
        emit(message)


def step(message: str) -> None:
    """Write the heading of a step of the work."""
    say(f"==> {message}")


def detail(message: str, depth: int = 1) -> None:
    """Write a line that belongs to the step above, indented *depth* levels."""
    say(f"{INDENT * depth}{message}")


def warn(message: str) -> None:
    """Write a warning (also when quiet)."""
    emit(f"WARNING: {message}")

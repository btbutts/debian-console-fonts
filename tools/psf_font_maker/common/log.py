"""Messages for the person running the tool: one line each, on stderr, written at once.

Standard output is left to results (a list of fonts, a directory a caller captures), so
everything here goes to standard error. Each line is flushed so that it shows up in a
build log as it happens, also when the line comes from a worker process.
"""

from __future__ import annotations

import sys

INDENT = "    "


def say(message: str) -> None:
    """Write *message* as one line on standard error."""
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()


def step(message: str) -> None:
    """Write the heading of a step of the work."""
    say(f"==> {message}")


def detail(message: str) -> None:
    """Write a line that belongs to the step above."""
    say(f"{INDENT}{message}")


def warn(message: str) -> None:
    """Write a warning."""
    say(f"WARNING: {message}")

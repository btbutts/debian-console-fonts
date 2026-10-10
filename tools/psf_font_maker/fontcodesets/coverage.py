"""Decide which code sets a font supports, from the symbols its BDF files define."""

from __future__ import annotations

import re
import tomllib
from importlib import resources
from typing import TYPE_CHECKING, Any

from psf_font_maker.common.errors import ToolError

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

# A font supports a code set when it has at least this many of the set's symbols.
THRESHOLD = 25
DATA_FILE = "codesets.toml"
ENCODING = re.compile(r"\s*ENCODING\s+([0-9]+)\s*")
LATIN_SETS = ("Lat15", "Lat2", "Lat38", "Lat7")


class CodesetError(ToolError):
    """The code set data or a font could not be read."""


def load_codesets() -> dict[str, list[int]]:
    """Return every code set's symbols, in the order the data file lists the sets."""
    text = resources.files(__package__).joinpath(DATA_FILE).read_text(encoding="utf-8")
    sections = tomllib.loads(text)
    return {name: _symbols_of(name, sections) for name in sections}


def _symbols_of(name: str, sections: dict[str, dict[str, Any]]) -> list[int]:
    """Return the symbols of set *name*, following the sets that it is the same as."""
    section = sections[name]
    while "same_as" in section:
        section = sections[section["same_as"]]
    return list(section["symbols"])


def text_symbols(text: str) -> set[int]:
    """Return the code points that the BDF font *text* defines."""
    codes: set[int] = set()
    for line in text.split("\n"):
        found = ENCODING.fullmatch(line)
        if found:
            codes.add(int(found.group(1)))
    return codes


def font_symbols(paths: Iterable[Path]) -> set[int]:
    """Return the code points that the BDF fonts define."""
    codes: set[int] = set()
    for path in paths:
        try:
            text = path.read_bytes().decode("latin-1")
        except OSError as exc:
            message = f"{path}: {exc.strerror}"
            raise CodesetError(message) from exc
        codes |= text_symbols(text)
    return codes


def supported_sets(symbols: set[int]) -> list[str]:
    """Return the names of the code sets that a font with *symbols* supports."""
    codesets = load_codesets()
    names = [
        name
        for name, wanted in codesets.items()
        if sum(1 for code in wanted if code in symbols) >= THRESHOLD
    ]
    has = set(names)
    result = list(names)
    latin = bool(has.intersection(LATIN_SETS))
    if latin and "CyrSlav" in has and "Hebrew" in has and "Arabic" in has:
        result.append("Uni1")
    if latin and "CyrSlav" in has and "Greek" in has:
        result.append("Uni2")
    if latin and "CyrSlav" in has and "CyrAsia" in has:
        result.append("Uni3")
    return result

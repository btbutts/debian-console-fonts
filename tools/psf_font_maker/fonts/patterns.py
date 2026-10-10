"""Word patterns with one ``%`` wildcard, as GNU make's ``filter`` uses them."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

WILDCARD = "%"


def matches(pattern: str, word: str) -> bool:
    """Return True if *word* fits *pattern*; ``%`` stands for any text (only the first one)."""
    if WILDCARD not in pattern:
        return pattern == word
    prefix, _, suffix = pattern.partition(WILDCARD)
    return len(word) >= len(prefix) + len(suffix) and word.startswith(prefix) and word.endswith(
        suffix
    )


def any_matches(patterns: Iterable[str], word: str) -> bool:
    """Return True if *word* fits at least one of the *patterns*."""
    return any(matches(pattern, word) for pattern in patterns)


def keep(patterns: Iterable[str], words: Iterable[str]) -> list[str]:
    """Return the *words* (in their order) that fit at least one pattern."""
    chosen = list(patterns)
    return [word for word in words if any_matches(chosen, word)]

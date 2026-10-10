"""Perl's ``rand``, reproduced exactly.

bdf2psf fills the glyphs of unused font positions with random bytes after
``srand(0)``. The output only matches the Perl tool byte for byte if the same
generator runs; Perl (5.20 and later) uses its own drand48 on every platform.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

MULTIPLIER = 0x5DEECE66D
INCREMENT = 0xB
STATE_BITS = 48
STATE_MASK = (1 << STATE_BITS) - 1
SEED_LOW_BITS = 0x330E
SEED_SHIFT = 16
SEED_MASK = 0xFFFFFFFF
BYTE_BITS = 8


def rand_bytes(seed: int = 0) -> Iterator[int]:
    """Yield what ``int(rand(256))`` returns, one value after another, after ``srand(seed)``."""
    state = SEED_LOW_BITS + ((seed & SEED_MASK) << SEED_SHIFT)
    while True:
        state = (state * MULTIPLIER + INCREMENT) & STATE_MASK
        yield state >> (STATE_BITS - BYTE_BITS)

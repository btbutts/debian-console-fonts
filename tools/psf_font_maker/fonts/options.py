"""What to build, as the user asked for it."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_FACES = ("Terminus%", "VGA%", "DejaVu%", "Fixed%")
DEFAULT_CODESETS = ("Uni1", "Uni2", "Uni3")
DEFAULT_DEJAVU_SIZES = (16, 20, 24, 28, 32, 40, 48, 64)
POOLS = ("good", "all")


@dataclass(frozen=True)
class DejaVuOptions:
    """How to render the DejaVu faces."""

    sizes: tuple[int, ...] = DEFAULT_DEJAVU_SIZES
    proportional: bool = False


@dataclass(frozen=True)
class Options:
    """The selection of fonts to build."""

    data: Path = Path("data")
    sources: Path = Path("sources.json")
    faces: tuple[str, ...] = DEFAULT_FACES
    codesets: tuple[str, ...] = DEFAULT_CODESETS
    skip: tuple[str, ...] = ()
    pool: str = "good"
    dejavu: DejaVuOptions = field(default_factory=DejaVuOptions)

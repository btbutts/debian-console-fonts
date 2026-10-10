"""The faces this project builds: which BDF fonts make each one, and for which code sets."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

DATA_FILE = "faces.toml"


@dataclass(frozen=True)
class UniVga:
    """A VGA face drawn from one Uni-VGA font, optionally enlarged."""

    font: str
    scale: int


@dataclass(frozen=True)
class Legacy:
    """The VGA faces, whose fonts depend on the code set."""

    faces: list[str]
    defaults: dict[str, str]
    codesets: dict[str, list[str]]
    bdfs: dict[str, dict[str, list[str]]]
    uni_vga: dict[str, UniVga]


@dataclass(frozen=True)
class Catalog:
    """The face tables of ``data/faces.toml``."""

    faces: dict[str, list[str]]
    legacy: Legacy
    codesets: list[str]
    good_faces: list[str]

    @property
    def all_faces(self) -> list[str]:
        """Every face: the ordinary ones, then the code-set dependent (VGA) ones."""
        return [*self.faces, *self.legacy.faces]


def load_catalog(data_dir: Path) -> Catalog:
    """Read the face tables from the data directory."""
    data = tomllib.loads((data_dir / DATA_FILE).read_text(encoding="utf-8"))
    legacy = data["legacy"]
    return Catalog(
        faces=data["faces"],
        legacy=Legacy(
            faces=legacy["faces"],
            defaults=legacy["defaults"],
            codesets=legacy["codesets"],
            bdfs=legacy["bdfs"],
            uni_vga={face: UniVga(**entry) for face, entry in legacy["uni_vga"].items()},
        ),
        codesets=data["sets"]["codesets"],
        good_faces=data["sets"]["good_faces"],
    )

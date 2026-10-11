"""Decide which fonts to build and exactly how to build each of them.

This is console-setup's Fonts/Makefile logic: a face is built for every code set it
covers (computed from its BDF fonts) among the ones asked for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from psf_font_maker.common.manifest import Manifest
from psf_font_maker.fontcodesets.coverage import supported_sets, text_symbols
from psf_font_maker.fonts.catalog import Catalog, load_catalog
from psf_font_maker.fonts.dejavu import PREFIX, dejavu_faces, styles
from psf_font_maker.fonts.patterns import any_matches, keep
from psf_font_maker.fonts.sources import BdfSpec, SourceTree

if TYPE_CHECKING:
    from pathlib import Path

    from psf_font_maker.fonts.options import Options

FULL = "Full"
UNI1 = "Uni1"
FULL_SIZE = 512
LEGACY_PREFIX = "VGA"
# Faces wider than 8 pixels are framebuffer-only fonts (bdf2psf --fb).
FRAMEBUFFER_WIDTHS = (6, 10, 11, 12, 14, 16, 20, 24, 28, 32, 40, 48, 64)
SYMBOL_SETS = ("ascii.set", "linux.set")


@dataclass(frozen=True)
class FontJob:
    """Everything needed to build one font."""

    name: str
    face: str
    bdfs: tuple[BdfSpec, ...]
    equivalents: tuple[Path, ...]
    symbols: tuple[str, ...]
    size: int
    framebuffer: bool


class Planner:
    """Works out the fonts for a set of options."""

    def __init__(self, options: Options, catalog: Catalog | None = None) -> None:
        """Read the face tables and locate the sources."""
        self.options = options
        self.tree = SourceTree(options.data, Manifest(options.sources))
        self.catalog = catalog or load_catalog(options.data)
        self._dejavu: dict[str, BdfSpec] | None = None
        self._coverage: dict[str, list[str]] = {}

    # --- which fonts -------------------------------------------------------------

    def _dejavu_wanted(self) -> bool:
        """Return True if any requested face pattern could match a DejaVu face."""
        probes = styles(self.options.dejavu)
        patterns = self.options.faces
        return any(pattern.startswith(PREFIX) for pattern in patterns) or any(
            any_matches(patterns, style) for style in probes
        )

    def dejavu(self) -> dict[str, BdfSpec]:
        """Return the rendered DejaVu faces, working out their heights on first use."""
        if self._dejavu is None:
            faces: dict[str, BdfSpec] = {}
            if self._dejavu_wanted():
                faces = dejavu_faces(self.tree.truetype_dir(), self.options.dejavu)
            self._dejavu = faces
        return self._dejavu

    def wants_truetype(self) -> bool:
        """Return True if a face pattern can select a DejaVu face (drawn from TrueType files).

        Unlike ``needs_truetype`` this does not render anything, so it can be asked before a
        FreeType has been chosen. It is a little generous: a face that ``skip`` leaves out
        still counts.
        """
        return self._dejavu_wanted()

    def needs_truetype(self) -> bool:
        """Return True if a selected face is rendered from a TrueType file (needs FreeType)."""
        rendered = self.dejavu()
        return any(face in rendered for face in self.selected())

    def pool(self) -> list[str]:
        """Return the faces to choose from."""
        faces = self.catalog.all_faces if self.options.pool == "all" else self.catalog.good_faces
        return [*faces, *self.dejavu()]

    def selected(self) -> list[str]:
        """Return the pool faces that fit the face patterns."""
        return keep(self.options.faces, self.pool())

    def is_legacy(self, face: str) -> bool:
        """Return True for the faces that take different fonts per code set (VGA)."""
        return face in self.catalog.legacy.faces

    def face_codesets(self, face: str) -> list[str]:
        """Return the code sets that *face* covers."""
        if self.is_legacy(face):
            return self.catalog.legacy.codesets[face]
        if face not in self._coverage:
            symbols = set().union(*(text_symbols(spec.text()) for spec in self.plain_bdfs(face)))
            self._coverage[face] = supported_sets(symbols)
        return self._coverage[face]

    def names(self) -> list[str]:
        """Return the names (``<Codeset>-<Face>``) of the fonts to build, sorted."""
        chosen = {
            f"{codeset}-{face}"
            for face in self.selected()
            for codeset in keep(self.options.codesets, self.face_codesets(face))
        }
        skip = self.options.skip
        return sorted(name for name in chosen if not any_matches(skip, name.partition("-")[2]))

    # --- which BDF fonts ---------------------------------------------------------

    def plain_bdfs(self, face: str) -> list[BdfSpec]:
        """Return the BDF fonts of a face that does not depend on the code set."""
        rendered = self.dejavu().get(face)
        if rendered is not None:
            return [rendered]
        return [BdfSpec(name, path=self.tree.bdf(name)) for name in self.catalog.faces[face]]

    def legacy_bdfs(self, face: str, codeset: str) -> list[BdfSpec]:
        """Return the BDF fonts of a VGA face for a code set."""
        legacy = self.catalog.legacy
        drawn = legacy.uni_vga.get(face)
        if drawn is not None:
            source = self.tree.bdf(drawn.font)
            if drawn.scale == 1:
                return [BdfSpec(drawn.font, path=source)]
            return [BdfSpec(f"{drawn.font}-x{drawn.scale}", path=source, doubled=True)]
        size = face[len(LEGACY_PREFIX) :]
        names = legacy.bdfs.get(codeset, {}).get(size) or [legacy.defaults[face]]
        return [BdfSpec(name, path=self.tree.bdf(name)) for name in names]

    # --- how to build ------------------------------------------------------------

    def _framebuffer(self, face: str) -> bool:
        """Return True if *face* is wider than 8 pixels."""
        widths = {*FRAMEBUFFER_WIDTHS, *self.options.dejavu.sizes}
        return face.endswith(tuple(f"x{width}" for width in widths))

    def _equivalents(self, codeset: str) -> tuple[Path, ...]:
        """Return the equivalents files of a code set that is not a Full one."""
        files = [self.tree.data_file("standard.equivalents")]
        if UNI1 in codeset:
            files.append(self.tree.data_file("arabic.equivalents"))
        return tuple(files)

    def job(self, name: str) -> FontJob:
        """Return the build instructions for the font called *name*."""
        codeset, _, face = name.partition("-")
        base = codeset.removeprefix(FULL)
        full = codeset.startswith(FULL)
        codeset_file = self.tree.codeset_file(base)
        equivalents = () if full else self._equivalents(codeset)
        symbols = (
            *(str(self.tree.data_file(item)) for item in SYMBOL_SETS),
            str(codeset_file),
            ":" + str(self.tree.data_file("useful.set")),
        )
        bdfs = self.legacy_bdfs(face, base) if self.is_legacy(face) else self.plain_bdfs(face)
        return FontJob(
            name=name,
            face=face,
            bdfs=tuple(bdfs),
            equivalents=equivalents,
            symbols=symbols,
            size=FULL_SIZE if full else int(codeset_file.suffix[1:]),
            framebuffer=self._framebuffer(face),
        )

    def jobs(self) -> list[FontJob]:
        """Return the build instructions for every font, sorted by name."""
        return [self.job(name) for name in self.names()]

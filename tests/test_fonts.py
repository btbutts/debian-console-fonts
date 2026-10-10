"""Tests for the ``fonts`` tool: choosing fonts and building them from the real sources.

These need the downloaded sources (run the downloader first); the DejaVu tests also need
freetype-py with a recent enough FreeType.
"""

from __future__ import annotations

import gzip
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from support import needs_freetype

from psf_font_maker.common.errors import ToolError
from psf_font_maker.common.psf_read import load_psf
from psf_font_maker.fonts.catalog import Catalog
from psf_font_maker.fonts.options import DejaVuOptions, Options
from psf_font_maker.fonts.patterns import keep, matches
from psf_font_maker.fonts.plan import Planner
from psf_font_maker.fonts.runner import build_all
from psf_font_maker.fonts.runner import convert as convert_job
from psf_font_maker.fonts.sources import BdfSpec, SourcesError
from psf_font_maker.main import main

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCES = ROOT / "sources.json"
HOMES = DATA / "fontsets"
LEGACY = HOMES / "debian-legacy-fonts"
DOCUMENTS = ("README.md", "AUTHORS.md", "LICENSE.md")
# console-setup is not used by the build. Where it has been downloaded (enable it in
# sources.json and run the downloader) it serves as a reference for a few checks.
CS = ROOT / "sources" / "console-setup"
reference = pytest.mark.skipif(
    not (CS / "Fonts" / "Makefile").is_file(),
    reason="console-setup is not downloaded (enable it in sources.json to run this check)",
)

pytestmark = pytest.mark.skipif(
    not (HOMES / "terminus-font" / "ter-u16n.bdf").is_file(), reason="fonts not downloaded"
)


MIN_BDFS = 50
DEFAULT_FONT_COUNT = 124  # Terminus, VGA, Fixed and the four DejaVu Mono styles
DEBIAN_DEJAVU_SIZES = {"30x16", "36x20", "43x24", "51x28", "59x32", "74x40", "89x48", "118x64"}
CUSTOM_CELL_WIDTH = 18
MIN_SAMPLE_FONTS = 25
DEJAVU_NAME = re.compile(r"Uni\d-(DejaVu\w*?)(\d+x\d+)$")
SAMPLE_CODESETS = ("Uni1", "Uni2", "Lat15", "Greek", "FullGreek", "CyrSlav", "Hebrew", "Arabic")


def options(**changes: object) -> Options:
    """Return the default options with some changed."""
    return replace(Options(data=DATA, sources=SOURCES), **changes)


def names(**changes: object) -> list[str]:
    """Return the font names that the given options select."""
    return Planner(options(**changes)).names()


def build(tmp_path: Path, **changes: object) -> Path:
    """Build the selected fonts into a fresh directory of *tmp_path* and return it."""
    out = tmp_path / f"out{len(list(tmp_path.iterdir()))}"
    build_all(Planner(options(**changes)).jobs(), out, workers=1)
    return out


def unpacked(directory: Path) -> dict[str, bytes]:
    """Return the decompressed fonts of *directory*, by name."""
    return {
        path.name[: -len(".psf.gz")]: gzip.decompress(path.read_bytes())
        for path in directory.glob("*.psf.gz")
    }


def percent_identical(first: Path, second: Path) -> float:
    """Return how many percent of the code points of two font directories have equal glyphs."""
    shared = same = 0
    for path in sorted(first.glob("*.psf.gz")):
        glyphs_a = load_psf(path)[2]
        glyphs_b = load_psf(second / path.name)[2]
        common = set(glyphs_a) & set(glyphs_b)
        shared += len(common)
        same += sum(1 for code in common if glyphs_a[code] == glyphs_b[code])
    return 100.0 * same / shared if shared else 100.0


# --------------------------------------------------------------------------
# patterns and selection
# --------------------------------------------------------------------------


def test_patterns_follow_makes_filter() -> None:
    """One % stands for any text; a pattern without % must match exactly."""
    assert matches("Terminus%", "Terminus16")
    assert matches("%VGA16", "TerminusBoldVGA16")
    assert matches("Fixed%5", "Fixed15")
    assert not matches("VGA%", "TerminusBoldVGA16")
    assert not matches("VGA16", "VGA161")
    assert keep(["VGA%", "Fixed13"], ["Fixed13", "VGA8", "Fixed14"]) == ["Fixed13", "VGA8"]


def test_selection_by_face_and_code_set() -> None:
    """Faces and code sets pick exactly the matching <Codeset>-<Face><size> names."""
    assert names(faces=("TerminusBoldVGA%",), codesets=("Uni2",)) == [
        "Uni2-TerminusBoldVGA14",
        "Uni2-TerminusBoldVGA16",
    ]
    assert names(faces=("Terminus16",), codesets=("Uni2", "Lat15")) == [
        "Lat15-Terminus16",
        "Uni2-Terminus16",
    ]
    # VGA% must not pick up TerminusBoldVGA*; FullGreek is its own code set.
    assert names(faces=("VGA16",), codesets=("Greek", "FullGreek")) == [
        "FullGreek-VGA16",
        "Greek-VGA16",
    ]


def test_skip_removes_faces() -> None:
    """SKIP leaves the matching faces out."""
    selected = names(
        faces=("TerminusBoldVGA%",), codesets=("Uni2", "Uni3"), skip=("TerminusBoldVGA16",)
    )
    assert selected == ["Uni2-TerminusBoldVGA14", "Uni3-TerminusBoldVGA14"]


def test_pool_good_versus_all() -> None:
    """POOL=all also offers faces outside console-setup's default set."""
    assert not names(faces=("FixedBold13",), codesets=("Uni2",))
    assert names(faces=("FixedBold13",), codesets=("Uni2",), pool="all") == ["Uni2-FixedBold13"]


@needs_freetype
def test_default_selection() -> None:
    """The defaults build four families in the three Unicode code sets."""
    selected = names()
    assert len(selected) == DEFAULT_FONT_COUNT
    assert {"Uni2-Terminus16", "Uni3-DejaVuBold118x64", "Uni1-VGA8", "Uni2-Fixed16"} <= set(
        selected
    )
    assert {name.split("-")[0] for name in selected} == {"Uni1", "Uni2", "Uni3"}


@reference
def test_coverage_matches_console_setups_precomputed_list() -> None:
    """For faces whose fonts are Debian's own, the code sets match console-setup's list."""
    soft = (CS / "Fonts" / "soft.Makefile").read_text()
    found = re.search(r"^I18N_FONT_NAMES\s*:=(.*)$", soft, re.MULTILINE)
    assert found is not None
    ours_only_debian = ("Courier", "Lucid", "Goha", "FixedBold16", "FixedBold24x12", "Fixed24x12")
    expected = {
        name
        for name in found.group(1).split()
        if name.split("-", 1)[1].startswith(ours_only_debian)
    }
    codesets = tuple(sorted({name.split("-")[0] for name in expected}))
    faces = tuple(sorted({name.split("-", 1)[1] for name in expected}))
    ours = set(names(faces=faces, codesets=codesets, pool="all"))
    assert ours == expected, (sorted(ours - expected)[:10], sorted(expected - ours)[:10])


def named_bdfs(catalog: Catalog) -> set[str]:
    """Return every BDF font the face table names."""
    fonts = {name for bdfs in catalog.faces.values() for name in bdfs}
    for sizes in catalog.legacy.bdfs.values():
        fonts |= {name for bdfs in sizes.values() for name in bdfs}
    return fonts | set(catalog.legacy.defaults.values())


def test_every_bdf_named_in_the_face_table_exists() -> None:
    """The tables name only fonts that can be found."""
    planner = Planner(options(pool="all"))
    catalog = planner.catalog
    wanted = named_bdfs(catalog) | {drawn.font for drawn in catalog.legacy.uni_vga.values()}
    assert len(wanted) > MIN_BDFS
    for name in sorted(wanted):
        assert planner.tree.bdf(name).is_file(), name


def test_the_legacy_fonts_directory_holds_only_fonts_that_are_used() -> None:
    """Every BDF in debian-legacy-fonts is named by the face table; the rest are documents."""
    used = named_bdfs(Planner(options(pool="all")).catalog)
    kept = {path.name for path in LEGACY.iterdir()}
    assert kept - used == set(DOCUMENTS)


def test_no_font_is_kept_in_two_places() -> None:
    """A BDF has one home: the legacy directory keeps only fonts nothing else supplies."""
    homes: dict[str, str] = {}
    for home in sorted(path for path in HOMES.iterdir() if path.is_dir()):
        for path in home.glob("*.bdf"):
            assert path.name not in homes, (path.name, homes[path.name], home.name)
            homes[path.name] = home.name


@pytest.mark.parametrize("home", sorted(path.name for path in HOMES.iterdir() if path.is_dir()))
def test_every_font_directory_has_its_three_documents(home: str) -> None:
    """Each directory of fonts has a README.md, an AUTHORS.md and a LICENSE.md, and no others."""
    documents = sorted(
        path.name for path in (HOMES / home).iterdir() if path.suffix in {".md", ".txt", ""}
        and path.is_file()
    )
    assert documents == sorted(DOCUMENTS)


def test_nothing_selected_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    """An empty face or code set list is reported, not replaced by the defaults."""
    arguments = ["fonts", "--data", str(DATA), "--sources", str(SOURCES), "--faces", "", "--list"]
    assert main(arguments) == 1
    assert "--faces: select at least one" in capsys.readouterr().err


def test_missing_sources_give_a_clear_error(tmp_path: Path) -> None:
    """Without the downloaded sources the error says how to get them."""
    tables = tmp_path / "data"
    shutil.copytree(DATA, tables, ignore=shutil.ignore_patterns("fontsets"))
    manifest = shutil.copy(SOURCES, tmp_path / "sources.json")  # its paths now lead nowhere
    with pytest.raises(SourcesError, match="fetch the sources first"):
        Planner(replace(Options(), data=tables, sources=Path(manifest))).tree.bdf("ter-u16n.bdf")


def test_a_wrong_data_directory_is_reported(tmp_path: Path) -> None:
    """Pointing at a directory without the font tables is an error, not an empty build."""
    with pytest.raises(SourcesError, match="font tables"):
        Planner(replace(Options(), data=tmp_path, sources=SOURCES))


def test_each_bdf_comes_from_the_right_place() -> None:
    """Each source has its own directory; the legacy directory holds only what has no source."""
    tree = Planner(options()).tree
    assert tree.bdf("ter-u16n.bdf") == HOMES / "terminus-font" / "ter-u16n.bdf"
    assert tree.bdf("8x13.bdf") == HOMES / "ucs-fonts" / "8x13.bdf"
    assert tree.bdf("u_vga16.bdf") == HOMES / "uni-vga" / "u_vga16.bdf"
    assert tree.bdf("8x13-IL2.bdf") == LEGACY / "8x13-IL2.bdf"
    assert tree.bdf("legacy14a.bdf") == LEGACY / "legacy14a.bdf"


# --------------------------------------------------------------------------
# building
# --------------------------------------------------------------------------


def test_output_names_follow_console_setup(tmp_path: Path) -> None:
    """Output files are named <Codeset>-<Face><size>.psf.gz."""
    out = build(tmp_path, faces=("Terminus20x10", "TerminusBoldVGA14"), codesets=("Uni2",))
    assert sorted(path.name for path in out.iterdir()) == [
        "Uni2-Terminus20x10.psf.gz",
        "Uni2-TerminusBoldVGA14.psf.gz",
    ]


@needs_freetype
def test_builds_are_reproducible(tmp_path: Path) -> None:
    """Two builds produce identical bytes, including the compressed files."""
    selection = {"faces": ("DejaVu30x16", "Fixed16", "VGA16"), "codesets": ("Uni2",)}
    first, second = build(tmp_path, **selection), build(tmp_path, **selection)
    for font in first.glob("*.psf.gz"):
        assert font.read_bytes() == (second / font.name).read_bytes()


@reference
@pytest.mark.skipif(shutil.which("perl") is None, reason="perl not installed")
def test_identical_to_console_setups_own_makefile(tmp_path: Path) -> None:
    """Fonts made from Debian's own BDFs come out as console-setup's Makefile makes them."""
    selection = {
        "faces": ("VGA8", "VGA14", "VGA28x16", "Courier13", "LucidBold15", "Goha16"),
        "codesets": SAMPLE_CODESETS,
        "pool": "all",
    }
    ours = unpacked(build(tmp_path, **selection))
    assert len(ours) >= MIN_SAMPLE_FONTS

    copy = tmp_path / "console-setup"
    shutil.copytree(CS, copy)
    subprocess.run(
        ["find", "Fonts/bdf", "-name", "*.bdf", "-exec", "touch", "{}", "+"], cwd=copy, check=True
    )
    fonts = copy / "Fonts"
    (fonts / "reference.mk").write_text(
        "include Makefile\n"
        ".PHONY: reference\n"
        "reference: $(addprefix $(fntdir)/,$(addsuffix .psf.gz,$(NAMES)))\n"
    )
    subprocess.run(
        ["make", "-s", "-j4", "-f", "reference.mk", f"NAMES={' '.join(ours)}", "reference"],
        cwd=fonts,
        check=True,
        capture_output=True,
    )
    different = [
        name
        for name, data in ours.items()
        if data != gzip.decompress((fonts / f"{name}.psf.gz").read_bytes())
    ]
    assert not different


def test_vga16_is_uni_vga_alone_and_vga32x16_is_its_enlargement(tmp_path: Path) -> None:
    """VGA16 and VGA32x16 use only Uni-VGA, for every code set."""
    planner = Planner(options(faces=("VGA16", "VGA32x16"), codesets=("Uni1", "Lat15")))
    for job in planner.jobs():
        assert [spec.path for spec in job.bdfs] == [HOMES / "uni-vga" / "u_vga16.bdf"]
        assert job.bdfs[0].doubled == (job.face == "VGA32x16")
    out = build(tmp_path, faces=("VGA16", "VGA32x16"), codesets=("Uni2",))
    assert sorted(path.name for path in out.iterdir()) == [
        "Uni2-VGA16.psf.gz",
        "Uni2-VGA32x16.psf.gz",
    ]


def test_other_vga_sizes_use_our_legacy_bdfs() -> None:
    """Uni-VGA has no 8 or 14 row font, so those sizes use the BDFs kept in debian-legacy-fonts."""
    planner = Planner(options(faces=("VGA8", "VGA14", "VGA28x16"), codesets=("Uni2",)))
    for job in planner.jobs():
        assert all(spec.path is not None and spec.path.parent == LEGACY for spec in job.bdfs)


# --------------------------------------------------------------------------
# DejaVu rendered from the TrueType files
# --------------------------------------------------------------------------


def dejavu_faces(selected: list[str]) -> dict[str, set[str]]:
    """Map each DejaVu face name to the set of <height>x<width> sizes among *selected*."""
    faces: dict[str, set[str]] = {}
    for name in selected:
        found = DEJAVU_NAME.match(name)
        if found:
            faces.setdefault(found.group(1), set()).add(found.group(2))
    return faces


@needs_freetype
def test_dejavu_mono_styles_use_debians_names_and_sizes() -> None:
    """Regular and Bold keep Debian's names; Oblique and BoldOblique are new; no proportional."""
    faces = dejavu_faces(names(faces=("DejaVu%",), codesets=("Uni2", "Uni3")))
    assert set(faces) == {"DejaVu", "DejaVuBold", "DejaVuOblique", "DejaVuBoldOblique"}
    assert all(sizes == DEBIAN_DEJAVU_SIZES for sizes in faces.values())


@needs_freetype
def test_dejavu_proportional_faces_are_opt_in() -> None:
    """The proportional faces appear only when asked for."""
    wanted = DejaVuOptions((16,), proportional=True)
    on = dejavu_faces(names(faces=("DejaVu%",), dejavu=wanted))
    assert {"DejaVuSerifBoldItalic", "DejaVuSansCondensedOblique"} <= set(on)
    off = dejavu_faces(names(faces=("DejaVu%",), dejavu=DejaVuOptions((16,))))
    assert not {"DejaVuSans", "DejaVuSerif"} & set(off)


@needs_freetype
def test_dejavu_custom_size() -> None:
    """DejaVu sizes other than Debian's are rendered; the height comes from the font."""
    faces = dejavu_faces(names(faces=("DejaVu%",), dejavu=DejaVuOptions((18, 22))))
    assert set(faces) == {"DejaVu", "DejaVuBold", "DejaVuOblique", "DejaVuBoldOblique"}
    for sizes in faces.values():
        assert {size.split("x")[1] for size in sizes} == {"18", "22"}


@reference
@needs_freetype
def test_dejavu_from_ttf_matches_debians_prerendered_fonts() -> None:
    """Rendering the TTFs gives the same fonts as converting Debian's pre-rendered BDFs."""
    planner = Planner(options(faces=("DejaVu30x16", "DejaVuBold59x32"), codesets=("Uni2", "Uni3")))
    prerendered = {"DejaVu30x16": "dejavu-u16.bdf", "DejaVuBold59x32": "dejavu-u32b.bdf"}
    for job in planner.jobs():
        debian = CS / "Fonts" / "bdf" / prerendered[job.face]
        theirs = replace(job, bdfs=(BdfSpec(job.face, path=debian),))
        assert convert_job(job)[0] == convert_job(theirs)[0], job.name


@needs_freetype
def test_dejavu_custom_size_is_built_as_a_framebuffer_font(tmp_path: Path) -> None:
    """A custom cell width gets the same treatment as Debian's sizes: --fb and the right cell."""
    out = build(
        tmp_path,
        faces=("DejaVu%",),
        codesets=("Uni2",),
        dejavu=DejaVuOptions((CUSTOM_CELL_WIDTH,)),
    )
    built = sorted(out.glob(f"Uni2-DejaVu[0-9]*x{CUSTOM_CELL_WIDTH}.psf.gz"))
    assert len(built) == 1
    width, height, glyphs = load_psf(built[0])
    assert width == CUSTOM_CELL_WIDTH
    assert str(height) in built[0].name
    assert ord("A") in glyphs


@needs_freetype
def test_dejavu_oblique_is_built(tmp_path: Path) -> None:
    """The Oblique faces are built and carry the same cell size as the upright ones."""
    out = build(
        tmp_path, faces=("DejaVu30x16", "DejaVuOblique30x16"), codesets=("Uni2",)
    )
    upright = load_psf(out / "Uni2-DejaVu30x16.psf.gz")
    oblique = load_psf(out / "Uni2-DejaVuOblique30x16.psf.gz")
    assert upright[:2] == oblique[:2]
    assert upright[2] != oblique[2]


def test_a_failing_font_is_named_in_the_error(tmp_path: Path) -> None:
    """If a font cannot be built the error says which."""
    planner = Planner(options(faces=("Fixed13",), codesets=("Uni2",)))
    job = planner.jobs()[0]
    broken = replace(job, symbols=(str(tmp_path / "missing.set"),))
    with pytest.raises(ToolError, match="Uni2-Fixed13"):
        build_all([broken], tmp_path / "out", workers=1)

"""Tests for the root Makefile, using the real downloaded sources.

Run `python3 .github/actions-scripts/dependencyDownloader.py --sources sources.json`
first; the tests are skipped when sources/ is not populated.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from psf_font_maker.common.psf_read import load_psf
from psf_font_maker.main import main as psf_font_maker
from psf_font_maker.otf2bdf import render
from psf_font_maker.otf2bdf.errors import RenderError

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "sources" / "console-setup"

pytestmark = [
    pytest.mark.skipif(not (CS / "Fonts" / "bdf2psf").is_file(), reason="sources/ not populated"),
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
]

DEFAULT_FONT_COUNT = 124  # Terminus, VGA, Fixed and the four DejaVu Mono styles
CUSTOM_CELL_WIDTH = 18
DEBIAN_DEJAVU_SIZES = {"30x16", "36x20", "43x24", "51x28", "59x32", "74x40", "89x48", "118x64"}
MIN_SAMPLE_FONTS = 25
SAMPLE_FACES = (
    "FACES=Terminus16 Terminus20x10 TerminusBoldVGA16 DejaVu30x16 DejaVuBold118x64 "
    "Fixed13 Fixed15 Fixed16 VGA8 VGA16 VGA28x16 VGA32x16"
)
SAMPLE_CODESETS = "CODESETS=Uni1 Uni2 Lat15 Greek FullGreek CyrSlav Hebrew Arabic"


EXACT = 100


def compare_outputs(first: Path, second: Path, minimum: float) -> int:
    """Compare the fonts built in two scratch directories; 0 means enough glyphs are identical."""
    options = ["--min-identical", str(minimum), "--quiet"]
    return psf_font_maker(["compare-fonts", str(first / "out"), str(second / "out"), *options])


def freetype_usable() -> bool:
    """Return True if freetype-py is installed with a FreeType new enough to render."""
    try:
        render.load_freetype()
    except RenderError:
        return False
    return True


needs_freetype = pytest.mark.skipif(
    not freetype_usable(), reason="rendering TrueType fonts needs a recent enough FreeType"
)


def run_make(
    tmp: Path, *args: str, cwd: Path = ROOT, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run make with BUILD and OUT inside *tmp* so the checkout stays clean."""
    return subprocess.run(
        ["make", "-s", f"BUILD={tmp / 'build'}", f"OUT={tmp / 'out'}", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def listed(tmp: Path, *args: str) -> set[str]:
    """Return the font names that ``make list`` reports for the given options."""
    return set(run_make(tmp, "list", *args).stdout.split())


def fresh(tmp: Path, name: str) -> Path:
    """Create and return an empty sub-directory of *tmp*."""
    path = tmp / name
    path.mkdir()
    return path


# --------------------------------------------------------------------------
# generated tables
# --------------------------------------------------------------------------


def test_faces_table_is_in_sync_with_console_setup() -> None:
    """mk/faces.mk matches what update-faces would generate now."""
    result = subprocess.run(
        [sys.executable, "-m", "psf_font_maker", "update-faces", "--check", "--root", str(ROOT)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT / "tools")},
    )
    assert result.returncode == 0, result.stderr


def test_faces_table_does_not_clobber_our_options() -> None:
    """Debian's FACES and CODESETS variables are renamed so our command-line options work."""
    text = (ROOT / "mk" / "faces.mk").read_text()
    assert not re.search(r"^(FACES|CODESETS)\s*:=", text, re.MULTILINE)
    assert re.search(r"^ALL_FACES\s*:=", text, re.MULTILINE)
    assert re.search(r"^ALL_CODESETS\s*:=", text, re.MULTILINE)


# --------------------------------------------------------------------------
# selection
# --------------------------------------------------------------------------


def test_selection_by_face_and_code_set(tmp_path: Path) -> None:
    """FACES and CODESETS pick exactly the matching <Codeset>-<Face><size> names."""
    assert listed(tmp_path, "FACES=TerminusBoldVGA%", "CODESETS=Uni2") == {
        "Uni2-TerminusBoldVGA14",
        "Uni2-TerminusBoldVGA16",
    }
    assert listed(tmp_path, "FACES=Terminus16", "CODESETS=Uni2 Lat15") == {
        "Uni2-Terminus16",
        "Lat15-Terminus16",
    }
    # VGA% must not pick up TerminusBoldVGA*; FullGreek is its own code set.
    assert listed(tmp_path, "FACES=VGA16", "CODESETS=Greek FullGreek") == {
        "Greek-VGA16",
        "FullGreek-VGA16",
    }


def test_skip_removes_names(tmp_path: Path) -> None:
    """SKIP leaves the matching faces out."""
    names = listed(
        tmp_path, "FACES=TerminusBoldVGA%", "CODESETS=Uni2 Uni3", "SKIP=TerminusBoldVGA16"
    )
    assert names == {"Uni2-TerminusBoldVGA14", "Uni3-TerminusBoldVGA14"}


def test_pool_good_versus_all(tmp_path: Path) -> None:
    """POOL=all also offers faces outside console-setup's default set."""
    assert not listed(tmp_path, "FACES=FixedBold13", "CODESETS=Uni2")
    assert listed(tmp_path, "FACES=FixedBold13", "CODESETS=Uni2", "POOL=all") == {
        "Uni2-FixedBold13"
    }


@needs_freetype
def test_default_selection(tmp_path: Path) -> None:
    """The defaults build four families in the three Unicode code sets."""
    names = listed(tmp_path)
    assert len(names) == DEFAULT_FONT_COUNT
    assert {"Uni2-Terminus16", "Uni3-DejaVuBold118x64", "Uni1-VGA8", "Uni2-Fixed16"} <= names
    assert {name.split("-")[0] for name in names} == {"Uni1", "Uni2", "Uni3"}


def test_coverage_matches_console_setup_soft_makefile(tmp_path: Path) -> None:
    """Code set coverage computed from the BDFs equals console-setup's precomputed list."""
    soft = (CS / "Fonts" / "soft.Makefile").read_text()
    names = re.search(r"^I18N_FONT_NAMES\s*:=(.*)$", soft, re.MULTILINE)
    good = re.search(r"^GOOD_FACES\s*:=(.*)$", (ROOT / "mk" / "faces.mk").read_text(), re.MULTILINE)
    assert names is not None
    assert good is not None
    faces = good.group(1).split()
    expected = {name for name in names.group(1).split() if name.split("-", 1)[1] in faces}
    codesets = sorted({name.split("-")[0] for name in expected})
    ours = listed(tmp_path, "USE_UPSTREAM=", "FACES=%", f"CODESETS={' '.join(codesets)}")
    assert ours == expected, (sorted(ours - expected)[:10], sorted(expected - ours)[:10])


# --------------------------------------------------------------------------
# build output
# --------------------------------------------------------------------------


@pytest.fixture(name="console_setup_copy", scope="module")
def console_setup_copy_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy console-setup's tree to a scratch directory so its own Makefile can run in it."""
    target = tmp_path_factory.mktemp("cs") / "console-setup"
    shutil.copytree(CS, target)
    subprocess.run(
        ["find", "Fonts/bdf", "-name", "*.bdf", "-exec", "touch", "{}", "+"],
        cwd=target,
        check=True,
    )
    return target


@pytest.mark.skipif(shutil.which("perl") is None, reason="perl not installed")
def test_byte_identical_to_console_setups_own_makefile(
    tmp_path: Path, console_setup_copy: Path
) -> None:
    """Same BDFs in, same bytes out as running console-setup's Makefile."""
    run_make(tmp_path, "USE_UPSTREAM=", "fonts", "-j4", SAMPLE_FACES, SAMPLE_CODESETS)
    built = sorted((tmp_path / "out").glob("*.psf.gz"))
    names = [path.name[: -len(".psf.gz")] for path in built]
    assert len(names) >= MIN_SAMPLE_FONTS

    fonts = console_setup_copy / "Fonts"
    (fonts / "reference.mk").write_text(
        "include Makefile\n"
        ".PHONY: reference\n"
        "reference: $(addprefix $(fntdir)/,$(addsuffix .psf.gz,$(NAMES)))\n"
    )
    subprocess.run(
        ["make", "-s", "-j4", "-f", "reference.mk", f"NAMES={' '.join(names)}", "reference"],
        cwd=fonts,
        check=True,
        capture_output=True,
    )
    different = [
        path.name for path in built if path.read_bytes() != (fonts / path.name).read_bytes()
    ]
    assert not different


@needs_freetype
def test_upstream_bdfs_replace_the_bundled_ones(tmp_path: Path) -> None:
    """USE_UPSTREAM decides which source each staged BDF comes from."""
    bundled = (CS / "Fonts" / "bdf").resolve()
    run_make(tmp_path, "list")
    stage = tmp_path / "build" / "Fonts" / "bdf"
    terminus = (ROOT / "sources" / "terminus-font" / "ter-u16n.bdf").resolve()
    assert (stage / "ter-u16n.bdf").resolve() == terminus
    ucs = (ROOT / "sources" / "ucs-fonts" / "8x13.bdf").resolve()
    assert (stage / "8x13.bdf").resolve() == ucs
    univga = (ROOT / "sources" / "uni-vga" / "u_vga16.bdf").resolve()
    assert (stage / "u_vga16.bdf").resolve() == univga

    other = fresh(tmp_path, "other")
    run_make(other, "list", "USE_UPSTREAM=")
    staged = (other / "build" / "Fonts" / "bdf" / "ter-u16n.bdf").resolve()
    assert staged == bundled / "ter-u16n.bdf"

    third = fresh(tmp_path, "third")
    run_make(third, "list", "USE_UPSTREAM=terminus-font")
    assert (third / "build" / "Fonts" / "bdf" / "8x13.bdf").resolve() == bundled / "8x13.bdf"


def test_terminus_release_differs_only_slightly_from_consolesetups_copy(tmp_path: Path) -> None:
    """Terminus 4.49.1 and console-setup's older copy agree on nearly every glyph."""
    args = ["fonts", "-j4", "FACES=Terminus16 TerminusBold20x10 Terminus32x16", "CODESETS=Uni2"]
    upstream = fresh(tmp_path, "up")
    bundled = fresh(tmp_path, "deb")
    run_make(upstream, *args)
    run_make(bundled, "USE_UPSTREAM=", *args)
    status = compare_outputs(upstream, bundled, 99)
    assert status == 0


@needs_freetype
def test_builds_are_reproducible(tmp_path: Path) -> None:
    """Two clean builds produce identical bytes."""
    first = fresh(tmp_path, "a")
    second = fresh(tmp_path, "b")
    for directory in (first, second):
        run_make(directory, "fonts", "FACES=DejaVu30x16 Fixed16 VGA16", "CODESETS=Uni2")
    for font in (first / "out").glob("*.psf.gz"):
        assert font.read_bytes() == (second / "out" / font.name).read_bytes()


def test_output_names_follow_console_setup(tmp_path: Path) -> None:
    """Output files are named <Codeset>-<Face><size>.psf.gz."""
    run_make(tmp_path, "fonts", "FACES=Terminus20x10 TerminusBoldVGA14", "CODESETS=Uni2")
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "Uni2-Terminus20x10.psf.gz",
        "Uni2-TerminusBoldVGA14.psf.gz",
    ]


# --------------------------------------------------------------------------
# goals that must not need the sources
# --------------------------------------------------------------------------


def bare_checkout(tmp: Path) -> Path:
    """Copy only the Makefile and its tables, with no sources/ at all."""
    bare = tmp / "bare"
    (bare / "mk").mkdir(parents=True)
    shutil.copy(ROOT / "Makefile", bare / "Makefile")
    for table in ("faces.mk", "dejavu.mk"):
        shutil.copy(ROOT / "mk" / table, bare / "mk" / table)
    return bare


def test_help_and_clean_need_no_sources(tmp_path: Path) -> None:
    """``make help`` and ``make clean`` work before the sources have been fetched."""
    bare = bare_checkout(tmp_path)
    assert "make fonts" in run_make(tmp_path, "help", cwd=bare).stdout
    run_make(tmp_path, "clean", cwd=bare)


def test_missing_sources_give_a_clear_error(tmp_path: Path) -> None:
    """Building without sources/ explains how to get them."""
    bare = bare_checkout(tmp_path)
    result = run_make(tmp_path, "list", cwd=bare, check=False)
    assert result.returncode != 0
    assert "fetch the sources first" in result.stderr


# --------------------------------------------------------------------------
# DejaVu rendered from the original TTFs
# --------------------------------------------------------------------------

DEJAVU_NAME = re.compile(r"Uni\d-(DejaVu\w*?)(\d+x\d+)$")


def dejavu_faces(names: set[str]) -> dict[str, set[str]]:
    """Map each DejaVu face name to the set of <height>x<width> sizes in *names*."""
    faces: dict[str, set[str]] = {}
    for name in names:
        match = DEJAVU_NAME.match(name)
        if match:
            faces.setdefault(match.group(1), set()).add(match.group(2))
    return faces


@needs_freetype
def test_dejavu_mono_styles_use_debians_names_and_sizes(tmp_path: Path) -> None:
    """Regular and Bold keep Debian's names; Oblique and BoldOblique are new; no proportional."""
    faces = dejavu_faces(listed(tmp_path))
    assert set(faces) == {"DejaVu", "DejaVuBold", "DejaVuOblique", "DejaVuBoldOblique"}
    assert all(sizes == DEBIAN_DEJAVU_SIZES for sizes in faces.values())


@needs_freetype
def test_dejavu_proportional_faces_are_opt_in(tmp_path: Path) -> None:
    """The proportional faces appear only with DEJAVU_PROPORTIONAL=1."""
    on = dejavu_faces(listed(tmp_path, "DEJAVU_PROPORTIONAL=1", "DEJAVU_SIZES=16"))
    assert {"DejaVuSerifBoldItalic", "DejaVuSansCondensedOblique"} <= set(on)
    off = dejavu_faces(listed(tmp_path, "DEJAVU_SIZES=16"))
    assert not {"DejaVuSans", "DejaVuSerif"} & set(off)


@needs_freetype
def test_dejavu_custom_size(tmp_path: Path) -> None:
    """DEJAVU_SIZES renders other cell widths; the height comes from the font."""
    faces = dejavu_faces(listed(tmp_path, "DEJAVU_SIZES=18 22"))
    assert set(faces) == {"DejaVu", "DejaVuBold", "DejaVuOblique", "DejaVuBoldOblique"}
    for sizes in faces.values():
        assert {size.split("x")[1] for size in sizes} == {"18", "22"}


@needs_freetype
def test_dejavu_from_ttf_matches_debians_prerendered_fonts(tmp_path: Path) -> None:
    """Rendering the TTFs gives the same glyphs as Debian's pre-rendered dejavu BDFs."""
    ours = fresh(tmp_path, "ttf")
    debian = fresh(tmp_path, "deb")
    args = ["fonts", "-j4", "FACES=DejaVu30x16 DejaVuBold59x32 DejaVu118x64", "CODESETS=Uni2 Uni3"]
    run_make(ours, *args)
    run_make(debian, "USE_UPSTREAM=terminus-font", *args)
    status = compare_outputs(ours, debian, EXACT)
    assert status == 0


@needs_freetype
def test_dejavu_custom_size_is_built_as_a_framebuffer_font(tmp_path: Path) -> None:
    """A custom cell width gets the same treatment as Debian's sizes: --fb and the right cell."""
    sizes = f"DEJAVU_SIZES={CUSTOM_CELL_WIDTH}"
    run_make(tmp_path, "fonts", sizes, "FACES=DejaVu%", "CODESETS=Uni2")
    built = sorted((tmp_path / "out").glob(f"Uni2-DejaVu[0-9]*x{CUSTOM_CELL_WIDTH}.psf.gz"))
    assert len(built) == 1
    width, height, glyphs = load_psf(built[0])
    assert width == CUSTOM_CELL_WIDTH
    assert str(height) in built[0].name
    assert ord("A") in glyphs


@needs_freetype
def test_dejavu_oblique_is_built(tmp_path: Path) -> None:
    """The Oblique faces are built and carry the same cell size as the upright ones."""
    run_make(tmp_path, "fonts", "FACES=DejaVu30x16 DejaVuOblique30x16", "CODESETS=Uni2")
    upright = load_psf(tmp_path / "out" / "Uni2-DejaVu30x16.psf.gz")
    oblique = load_psf(tmp_path / "out" / "Uni2-DejaVuOblique30x16.psf.gz")
    assert upright[:2] == oblique[:2] == (16, 30)
    assert upright[2] != oblique[2]


# --------------------------------------------------------------------------
# VGA from Uni-VGA
# --------------------------------------------------------------------------

MIN_VGA_SIMILARITY = 99.5
UNI_VGA_BDF = ROOT / "sources" / "uni-vga" / "u_vga16.bdf"


@pytest.mark.skipif(not UNI_VGA_BDF.is_file(), reason="sources/uni-vga not populated")
def test_vga16_and_vga32x16_come_from_uni_vga(tmp_path: Path) -> None:
    """VGA16 and VGA32x16 use only Uni-VGA and stay close to console-setup's versions."""
    double = CS / "Fonts" / "bdf" / "u_vga16-double.bdf"
    before = double.read_bytes()
    ours = fresh(tmp_path, "ours")
    debian = fresh(tmp_path, "deb")
    args = ["fonts", "-j4", "FACES=VGA16 VGA32x16", "CODESETS=Uni2 Lat15 Greek"]
    run_make(ours, *args)
    run_make(debian, "USE_UPSTREAM=terminus-font", *args)
    status = compare_outputs(ours, debian, MIN_VGA_SIMILARITY)
    assert status == 0
    assert double.read_bytes() == before  # the generated file never writes through the symlink


def test_other_vga_sizes_keep_the_legacy_bdfs(tmp_path: Path) -> None:
    """Uni-VGA has no 8 or 14 row font, so VGA8, VGA14 and VGA28x16 are unchanged."""
    ours = fresh(tmp_path, "ours")
    debian = fresh(tmp_path, "deb")
    args = ["fonts", "-j4", "FACES=VGA8 VGA14 VGA28x16", "CODESETS=Uni2"]
    run_make(ours, *args)
    run_make(debian, "USE_UPSTREAM=", *args)
    status = compare_outputs(ours, debian, 100)
    assert status == 0

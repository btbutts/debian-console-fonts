"""Tests for the root Makefile, using the real downloaded sources.

Run `python3 .github/actions-scripts/dependencyDownloader.py --sources sources.json`
first; the tests are skipped when sources/ is not populated.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "sources" / "console-setup"

pytestmark = [
    pytest.mark.skipif(not (CS / "Fonts" / "bdf2psf").is_file(), reason="sources/ not populated"),
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
    pytest.mark.skipif(shutil.which("perl") is None, reason="perl not installed"),
]


def load_tool(name: str):
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compare_fonts = load_tool("compare-fonts")


def run_make(tmp: Path, *args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["make", "-s", f"BUILD={tmp / 'build'}", f"OUT={tmp / 'out'}", *args],
        cwd=cwd, capture_output=True, text=True, check=check,
    )


def listed(tmp: Path, *args: str) -> set[str]:
    return set(run_make(tmp, "list", *args).stdout.split())


# --------------------------------------------------------------------------
# generated tables
# --------------------------------------------------------------------------


def test_faces_table_is_in_sync_with_console_setup():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "update-faces.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_faces_table_does_not_clobber_our_options():
    text = (ROOT / "mk" / "faces.mk").read_text()
    assert not re.search(r"^(FACES|CODESETS)\s*:=", text, re.M)
    assert re.search(r"^ALL_FACES\s*:=", text, re.M) and re.search(r"^ALL_CODESETS\s*:=", text, re.M)


# --------------------------------------------------------------------------
# selection
# --------------------------------------------------------------------------


def test_selection_by_face_and_code_set(tmp_path):
    assert listed(tmp_path, "FACES=TerminusBoldVGA%", "CODESETS=Uni2") == {
        "Uni2-TerminusBoldVGA14", "Uni2-TerminusBoldVGA16",
    }
    assert listed(tmp_path, "FACES=Terminus16", "CODESETS=Uni2 Lat15") == {
        "Uni2-Terminus16", "Lat15-Terminus16",
    }
    # VGA% must not pick up TerminusBoldVGA*; FullGreek is its own code set.
    assert listed(tmp_path, "FACES=VGA16", "CODESETS=Greek FullGreek") == {
        "Greek-VGA16", "FullGreek-VGA16",
    }


def test_skip_removes_names(tmp_path):
    names = listed(tmp_path, "FACES=TerminusBoldVGA%", "CODESETS=Uni2 Uni3", "SKIP=TerminusBoldVGA16")
    assert names == {"Uni2-TerminusBoldVGA14", "Uni3-TerminusBoldVGA14"}


def test_pool_good_versus_all(tmp_path):
    assert listed(tmp_path, "FACES=FixedBold13", "CODESETS=Uni2") == set()  # not in console-setup's default set
    assert listed(tmp_path, "FACES=FixedBold13", "CODESETS=Uni2", "POOL=all") == {"Uni2-FixedBold13"}


def test_default_selection(tmp_path):
    names = listed(tmp_path)
    assert len(names) == 92
    assert {"Uni2-Terminus16", "Uni3-DejaVuBold118x64", "Uni1-VGA8", "Uni2-Fixed16"} <= names
    assert {n.split("-")[0] for n in names} == {"Uni1", "Uni2", "Uni3"}


def test_coverage_matches_console_setup_soft_makefile(tmp_path):
    """Code set coverage computed from the BDFs equals console-setup's precomputed list."""
    soft = (CS / "Fonts" / "soft.Makefile").read_text()
    line = re.search(r"^I18N_FONT_NAMES\s*:=(.*)$", soft, re.M).group(1).split()
    good = re.search(r"^GOOD_FACES\s*:=(.*)$", (ROOT / "mk" / "faces.mk").read_text(), re.M).group(1).split()
    expected = {name for name in line if name.split("-", 1)[1] in good}
    codesets = sorted({name.split("-")[0] for name in expected})
    ours = listed(tmp_path, "USE_UPSTREAM=", "FACES=%", f"CODESETS={' '.join(codesets)}")
    assert ours == expected, (sorted(ours - expected)[:10], sorted(expected - ours)[:10])


# --------------------------------------------------------------------------
# build output
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def console_setup_copy(tmp_path_factory):
    """A scratch copy of console-setup's tree, so its own Makefile can run in it."""
    target = tmp_path_factory.mktemp("cs") / "console-setup"
    shutil.copytree(CS, target)
    subprocess.run(["find", "Fonts/bdf", "-name", "*.bdf", "-exec", "touch", "{}", "+"], cwd=target, check=True)
    return target


SAMPLE = ["FACES=Terminus16 Terminus20x10 TerminusBoldVGA16 DejaVu30x16 DejaVuBold118x64 Fixed13 Fixed15 Fixed16 VGA8 VGA16 VGA28x16 VGA32x16",
          "CODESETS=Uni1 Uni2 Lat15 Greek FullGreek CyrSlav Hebrew Arabic"]


def test_byte_identical_to_console_setups_own_makefile(tmp_path, console_setup_copy):
    """Same BDFs in, same bytes out as running console-setup's Makefile."""
    run_make(tmp_path, "USE_UPSTREAM=", "fonts", "-j4", *SAMPLE)
    names = sorted(p.name[: -len(".psf.gz")] for p in (tmp_path / "out").glob("*.psf.gz"))
    assert len(names) >= 25

    fonts = console_setup_copy / "Fonts"
    (fonts / "reference.mk").write_text(
        "include Makefile\n"
        ".PHONY: reference\n"
        "reference: $(addprefix $(fntdir)/,$(addsuffix .psf.gz,$(NAMES)))\n"
    )
    subprocess.run(["make", "-s", "-j4", "-f", "reference.mk", f"NAMES={' '.join(names)}", "reference"],
                   cwd=fonts, check=True, capture_output=True)
    different = [n for n in names if (tmp_path / "out" / f"{n}.psf.gz").read_bytes() != (fonts / f"{n}.psf.gz").read_bytes()]
    assert different == []


def test_upstream_bdfs_replace_the_bundled_ones(tmp_path):
    run_make(tmp_path, "list")
    stage = tmp_path / "build" / "Fonts" / "bdf"
    assert (stage / "ter-u16n.bdf").resolve() == (ROOT / "sources" / "terminus-font" / "ter-u16n.bdf").resolve()
    assert (stage / "8x13.bdf").resolve() == (CS / "Fonts" / "bdf" / "8x13.bdf").resolve()  # ucs-fonts is opt-in

    other = tmp_path / "other"
    other.mkdir()
    run_make(other, "list", "USE_UPSTREAM=")
    assert (other / "build" / "Fonts" / "bdf" / "ter-u16n.bdf").resolve() == (CS / "Fonts" / "bdf" / "ter-u16n.bdf").resolve()

    third = tmp_path / "third"
    third.mkdir()
    run_make(third, "list", "USE_UPSTREAM=terminus-font ucs-fonts")
    assert (third / "build" / "Fonts" / "bdf" / "8x13.bdf").resolve() == (ROOT / "sources" / "ucs-fonts" / "8x13.bdf").resolve()


def test_terminus_release_differs_only_slightly_from_consolesetups_copy(tmp_path):
    args = ["fonts", "-j4", "FACES=Terminus16 TerminusBold20x10 Terminus32x16", "CODESETS=Uni2"]
    upstream, bundled = tmp_path / "up", tmp_path / "deb"
    upstream.mkdir(), bundled.mkdir()
    run_make(upstream, *args)
    run_make(bundled, "USE_UPSTREAM=", *args)
    assert compare_fonts.main([str(upstream / "out"), str(bundled / "out"), "--min-identical", "99", "--quiet"]) == 0


def test_builds_are_reproducible(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    for directory in (first, second):
        run_make(directory, "fonts", "FACES=DejaVu30x16 Fixed16 VGA16", "CODESETS=Uni2")
    for font in (first / "out").glob("*.psf.gz"):
        assert font.read_bytes() == (second / "out" / font.name).read_bytes()


def test_output_names_follow_console_setup(tmp_path):
    run_make(tmp_path, "fonts", "FACES=Terminus20x10 TerminusBoldVGA14", "CODESETS=Uni2")
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "Uni2-Terminus20x10.psf.gz", "Uni2-TerminusBoldVGA14.psf.gz",
    ]


# --------------------------------------------------------------------------
# goals that must not need the sources
# --------------------------------------------------------------------------


def test_help_and_clean_need_no_sources(tmp_path):
    bare = tmp_path / "bare"
    (bare / "mk").mkdir(parents=True)
    shutil.copy(ROOT / "Makefile", bare / "Makefile")
    shutil.copy(ROOT / "mk" / "faces.mk", bare / "mk" / "faces.mk")
    assert "make fonts" in run_make(tmp_path, "help", cwd=bare).stdout
    run_make(tmp_path, "clean", cwd=bare)


def test_missing_sources_give_a_clear_error(tmp_path):
    bare = tmp_path / "bare"
    (bare / "mk").mkdir(parents=True)
    shutil.copy(ROOT / "Makefile", bare / "Makefile")
    shutil.copy(ROOT / "mk" / "faces.mk", bare / "mk" / "faces.mk")
    result = run_make(tmp_path, "list", cwd=bare, check=False)
    assert result.returncode != 0
    assert "fetch the sources first" in result.stderr

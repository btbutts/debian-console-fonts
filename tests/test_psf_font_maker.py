"""Tests for tools/psf_font_maker, the Python replacement for bdf2psf.

The last group runs the Perl bdf2psf from tools/bdf2psf and the Python port on the
same inputs and requires identical bytes; it needs the downloaded sources, make
and perl.
"""

from __future__ import annotations

import itertools
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from psf_font_maker.bdf2psf.bdf_reader import GlyphSet, read_bdf
from psf_font_maker.bdf2psf.classify import FRAMEBUFFER, TEXT_MODE
from psf_font_maker.bdf2psf.convert import Request, build, convert, normalise_size
from psf_font_maker.bdf2psf.equivalence import Equivalence, printable
from psf_font_maker.bdf2psf.errors import ConversionError, EquivalenceError, FontFormatError
from psf_font_maker.bdf2psf.random48 import rand_bytes
from psf_font_maker.common import psf
from psf_font_maker.main import main

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "reference"

# srand(0); print join(",", map { int(rand(256)) } 1..12)   (Perl 5.34, same on 5.20+)
PERL_RANDOM = [43, 191, 24, 222, 147, 201, 177, 94, 223, 190, 114, 90]

SMALL_HEIGHT = 4
SMALL_WIDTH = 8
LETTER_A = 0x41
LETTER_B = 0x42
SPACE = 0x20
GREEK_ALPHA = 0x391
POSITION_COUNT = 256
PSF1_HEADER_SIZE = 4
TERMINATOR = b"\xff\xff"
TABLE_BYTES = 2
PSF2_HEADER_SIZE = 32
WIDE_WIDTH = 12
SAMPLE_COMMANDS = 40


def tiny_bdf(width: int = SMALL_WIDTH, glyphs: dict[int, list[str]] | None = None) -> str:
    """Return the text of a BDF with a few glyphs, SMALL_HEIGHT rows high."""
    glyphs = glyphs or {LETTER_A: ["18", "24", "7E", "42"], LETTER_B: ["7C", "42", "7C", "42"]}
    out = [
        "STARTFONT 2.1",
        "FONT tiny",
        "STARTPROPERTIES 3",
        f"FONT_ASCENT {SMALL_HEIGHT - 1}",
        "FONT_DESCENT 1",
        f"AVERAGE_WIDTH {width * 10}",
        "ENDPROPERTIES",
        f"CHARS {len(glyphs)}",
    ]
    for code, rows in glyphs.items():
        out += [
            f"STARTCHAR u{code:04X}",
            f"ENCODING {code}",
            "SWIDTH 500 0",
            f"DWIDTH {width} 0",
            f"BBX {width} {SMALL_HEIGHT} 0 -1",
            "BITMAP",
            *rows,
            "ENDCHAR",
        ]
    out.append("ENDFONT")
    return "\n".join(out) + "\n"


@pytest.fixture(name="inputs")
def inputs_fixture(tmp_path: Path) -> dict[str, Path]:
    """Write a small font, an equivalents file and a symbols file."""
    files = {
        "bdf": tmp_path / "tiny.bdf",
        "equiv": tmp_path / "equiv",
        "symbols": tmp_path / "symbols",
    }
    files["bdf"].write_text(tiny_bdf())
    files["equiv"].write_text("U+0041 U+0391  # Latin A and Greek Alpha\n")
    files["symbols"].write_text("U+0041\nU+0042\nU+0391\n")
    return files


def request_for(inputs: dict[str, Path], size: int = POSITION_COUNT, font_type: int = TEXT_MODE):
    """Return a Request using the files from the ``inputs`` fixture."""
    return Request(
        bdfs=[inputs["bdf"]],
        equivalents=[inputs["equiv"]],
        symbols=[str(inputs["symbols"])],
        font_size=size,
        font_type=font_type,
    )


# --------------------------------------------------------------------------
# pieces
# --------------------------------------------------------------------------


def test_random_matches_perl() -> None:
    """The filler bytes are the ones Perl's rand produces after srand(0)."""
    assert list(itertools.islice(rand_bytes(0), len(PERL_RANDOM))) == PERL_RANDOM


def test_printable_follows_bdf2psf() -> None:
    """Control characters, DEL and the C1 range are not printable."""
    assert printable(0x20)
    assert printable(0x7E)
    assert not printable(0x7F)
    assert not printable(0x9F)
    assert printable(0xA0)
    assert not printable(0x1F)


def test_equivalence_classes_merge_in_bdf2psfs_order(tmp_path: Path) -> None:
    """Later symbols are put in front, and two classes are merged symbol by symbol."""
    path = tmp_path / "equiv"
    path.write_text("U+0041 U+0391 U+0410\nU+0042 U+0392\nU+0391 U+0392\n")
    classes = Equivalence()
    classes.load(path)
    assert classes.of(0x41) is classes.of(0x391) is classes.of(0x410)
    assert classes.of(0x41) is classes.of(0x42)
    assert sorted(classes.of(0x41)) == [0x41, 0x42, 0x391, 0x392, 0x410]


def test_equivalence_syntax_error_names_the_line(tmp_path: Path) -> None:
    """Text after the last U+ code is reported with its line number."""
    path = tmp_path / "equiv"
    path.write_text("U+0041 U+0391\nU+0042 nonsense\n")
    with pytest.raises(EquivalenceError, match="line 2"):
        Equivalence().load(path)


def test_box_drawing_and_cp437_lookups() -> None:
    """Symbols in the box-drawing blocks, and CP437 symbols, are recognised."""
    classes = Equivalence()
    assert classes.is_box_drawings(0x2500)
    assert classes.is_box_drawings(0x2594)
    assert not classes.is_box_drawings(0x2593)
    assert classes.cp437(0x263A) == 1
    assert classes.cp437(SPACE) == SPACE
    assert classes.cp437(0x3042) == 0


def test_bdf_reader_places_rows_in_the_cell(tmp_path: Path) -> None:
    """A glyph with a baseline offset is padded to the cell height."""
    path = tmp_path / "tiny.bdf"
    path.write_text(tiny_bdf())
    glyph_set = GlyphSet()
    read_bdf(path, glyph_set, lambda _: None)
    assert (glyph_set.width, glyph_set.height) == (SMALL_WIDTH, SMALL_HEIGHT)
    assert glyph_set.glyphs[LETTER_A] == [0x18, 0x24, 0x7E, 0x42]


def test_first_font_wins(tmp_path: Path) -> None:
    """When two fonts define a code point the first one is kept."""
    first, second = tmp_path / "first.bdf", tmp_path / "second.bdf"
    first.write_text(tiny_bdf(glyphs={LETTER_A: ["01", "01", "01", "01"]}))
    second.write_text(tiny_bdf(glyphs={LETTER_A: ["02", "02", "02", "02"], LETTER_B: ["03"] * 4}))
    glyph_set = GlyphSet()
    for path in (first, second):
        read_bdf(path, glyph_set, lambda _: None)
    assert glyph_set.glyphs[LETTER_A] == [1, 1, 1, 1]
    assert glyph_set.glyphs[LETTER_B] == [3, 3, 3, 3]


def test_fonts_of_different_size_are_rejected(tmp_path: Path) -> None:
    """Merging fonts needs the same cell height and width."""
    first, second = tmp_path / "first.bdf", tmp_path / "second.bdf"
    first.write_text(tiny_bdf())
    second.write_text(tiny_bdf(width=WIDE_WIDTH, glyphs={LETTER_A: ["FF00"] * SMALL_HEIGHT}))
    glyph_set = GlyphSet()
    read_bdf(first, glyph_set, lambda _: None)
    with pytest.raises(FontFormatError, match="width is not the same"):
        read_bdf(second, glyph_set, lambda _: None)


def test_wrong_row_count_is_rejected(tmp_path: Path) -> None:
    """A glyph with too few rows for its box is an error."""
    path = tmp_path / "bad.bdf"
    path.write_text(tiny_bdf(glyphs={LETTER_A: ["18", "24"]}))
    with pytest.raises(FontFormatError, match="invalid number of rows"):
        read_bdf(path, GlyphSet(), lambda _: None)


@pytest.mark.parametrize(
    ("font_type", "size", "result"),
    [(TEXT_MODE, 100, 256), (TEXT_MODE, 257, 512), (FRAMEBUFFER, 1024, 1024)],
)
def test_sizes_are_rounded(font_type: int, size: int, result: int) -> None:
    """Fonts have 256 or 512 positions unless they are larger framebuffer fonts."""
    assert normalise_size(font_type, size) == result


def test_text_mode_fonts_cannot_have_many_positions() -> None:
    """Only framebuffer fonts may have more than 512 positions."""
    with pytest.raises(ConversionError, match="non-framebuffer"):
        normalise_size(TEXT_MODE, 1024)


# --------------------------------------------------------------------------
# whole fonts
# --------------------------------------------------------------------------


def test_psf1_layout_and_unicode_table(inputs: dict[str, Path]) -> None:
    """An 8-pixel font with 256 positions is a PSF1 file with the symbols in its table."""
    data = convert(request_for(inputs))
    assert data[:2] == psf.PSF1_MAGIC
    assert data[2:4] == bytes((psf.PSF1_MODE_HAS_TABLE, SMALL_HEIGHT))
    glyphs = data[PSF1_HEADER_SIZE : PSF1_HEADER_SIZE + POSITION_COUNT * SMALL_HEIGHT]
    assert bytes((0x18, 0x24, 0x7E, 0x42)) == glyphs[LETTER_A * 4 : LETTER_A * 4 + 4]
    table = data[PSF1_HEADER_SIZE + POSITION_COUNT * SMALL_HEIGHT :]
    assert table.count(TERMINATOR) == POSITION_COUNT
    alpha = GREEK_ALPHA.to_bytes(TABLE_BYTES, "little")
    assert alpha in table


def test_equivalent_symbols_share_one_position(inputs: dict[str, Path]) -> None:
    """Greek Alpha, equivalent to A, takes no position of its own."""
    layout = build(request_for(inputs))
    holders = [cls for cls in layout.classes if cls and GREEK_ALPHA in cls]
    assert len(holders) == 1
    assert LETTER_A in holders[0]


def test_wide_font_is_psf2(tmp_path: Path) -> None:
    """A font that is not 8 pixels wide is written as PSF2."""
    bdf = tmp_path / "wide.bdf"
    bdf.write_text(tiny_bdf(width=WIDE_WIDTH, glyphs={LETTER_A: ["F0F0"] * SMALL_HEIGHT}))
    symbols = tmp_path / "symbols"
    symbols.write_text("U+0041\n")
    request = Request(
        bdfs=[bdf],
        equivalents=[Path(os.devnull)],
        symbols=[str(symbols)],
        font_size=POSITION_COUNT,
        font_type=FRAMEBUFFER,
    )
    data = convert(request)
    assert data[:4] == psf.PSF2_MAGIC
    assert int.from_bytes(data[8:12], "little") == psf.PSF2_HEADER_SIZE
    assert int.from_bytes(data[24:28], "little") == SMALL_HEIGHT
    assert int.from_bytes(data[28:32], "little") == WIDE_WIDTH
    assert len(data) > PSF2_HEADER_SIZE + POSITION_COUNT * 2 * SMALL_HEIGHT


def test_missing_symbols_are_reported(inputs: dict[str, Path]) -> None:
    """A requested symbol with no glyph is warned about unless its file is marked quiet."""
    inputs["symbols"].write_text("U+0041\nU+0100\n")
    loud = request_for(inputs)
    build(loud)
    assert any("U+0100: no glyph defined" in text for text in loud.warnings)
    quiet = request_for(inputs)
    quiet.symbols = [":" + str(inputs["symbols"])]
    build(quiet)
    assert not quiet.warnings


def test_command_line_writes_font_log_and_table(
    inputs: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The bdf2psf command takes the Perl tool's arguments."""
    inputs["symbols"].write_text("U+0041\nU+0100\n")
    out, log, sfm = tmp_path / "out.psf", tmp_path / "out.log", tmp_path / "out.sfm"
    argv = [
        "bdf2psf",
        "--log",
        str(log),
        str(inputs["bdf"]),
        str(inputs["equiv"]),
        str(inputs["symbols"]),
        str(POSITION_COUNT),
        str(out),
        str(sfm),
    ]
    assert main(argv) == 0
    assert out.read_bytes()[:2] == psf.PSF1_MAGIC
    assert "U+0100: no glyph defined" in log.read_text()
    assert "U+0100: no glyph defined" in capsys.readouterr().err
    assert sfm.read_text().splitlines()[LETTER_A].startswith("0x41")


def test_command_line_reports_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A missing file is an error message and status 1, not a traceback."""
    argv = ["bdf2psf", str(tmp_path / "none.bdf"), "/dev/null", "/dev/null", "256", "x.psf"]
    assert main(argv) == 1
    assert "psf_font_maker:" in capsys.readouterr().err


# --------------------------------------------------------------------------
# identical to the Perl tool
# --------------------------------------------------------------------------

SOURCES = ROOT / "sources" / "console-setup" / "Fonts"
perl_comparison = pytest.mark.skipif(
    not (SOURCES / "fontsets").is_dir()
    or shutil.which("perl") is None
    or shutil.which("make") is None,
    reason="needs sources/, perl and make",
)

SAMPLE_FACES = (
    "FACES=Terminus16 Terminus32x16 TerminusBoldVGA14 Fixed13 Fixed16 Fixed18 VGA8 VGA14 "
    "VGA28x16 VGA32x16 VGA16 FixedOblique13"
)
SAMPLE_CODESETS = "CODESETS=Uni1 Uni2 Lat15 Greek FullGreek Hebrew Arabic CyrSlav"


def recipe_commands(tmp_path: Path) -> list[list[str]]:
    """Return the arguments of the bdf2psf commands that ``make fonts`` would run."""
    common = ["make", "-s", f"BUILD={tmp_path / 'build'}", f"OUT={tmp_path / 'out'}"]
    args = [SAMPLE_FACES, SAMPLE_CODESETS, "USE_UPSTREAM=terminus-font uni-vga ucs-fonts"]
    subprocess.run([*common, "list", *args], cwd=ROOT, capture_output=True, check=True)
    dry = subprocess.run(
        [*common, "-n", "fonts", *args], cwd=ROOT, capture_output=True, text=True, check=True
    )
    commands = []
    for line in dry.stdout.replace("\\\n", " ").splitlines():
        words = shlex.split(line)
        if "bdf2psf" in words:
            end = next(i for i, word in enumerate(words) if word.startswith("2>"))
            commands.append(words[words.index("bdf2psf") + 1 : end])
    return commands


@perl_comparison
def test_output_is_identical_to_the_perl_tool(tmp_path: Path) -> None:
    """Every font in a broad sample comes out byte for byte as the Perl bdf2psf makes it."""
    commands = recipe_commands(tmp_path)
    assert len(commands) >= SAMPLE_COMMANDS
    for index, words in enumerate(commands):
        reference, ours = tmp_path / f"{index}.perl", tmp_path / f"{index}.python"
        perl = ["perl", str(REFERENCE / "bdf2psf"), *words[:-1], str(reference)]
        subprocess.run(perl, capture_output=True, check=True)
        assert main(["bdf2psf", *words[:-1], str(ours)]) == 0, words[-1]
        assert ours.read_bytes() == reference.read_bytes(), words[-1]


FONT_SETS = (
    "ter-u16n.bdf",
    "u_vga16.bdf",
    "8x13-IL2.bdf+8x13.bdf+8x13c.bdf",
    "legacy14e.bdf+legacy14a.bdf+legacy14g.bdf+legacy14l.bdf+legacy14c.bdf",
    "georgian16.bdf+unifont.bdf+h16.bdf+etl16-unicode.bdf",
    "Goha16.bdf",
)


@perl_comparison
def test_fontcodesets_matches_the_perl_tool(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """The code sets reported for real fonts are those the Perl fontcodesets reports."""
    common = ["make", "-s", f"BUILD={tmp_path / 'build'}", f"OUT={tmp_path / 'out'}", "list"]
    subprocess.run(common, cwd=ROOT, capture_output=True, check=True)
    staged = tmp_path / "build" / "Fonts"
    for fonts in FONT_SETS:
        perl = subprocess.run(
            ["perl", str(REFERENCE / "fontcodesets"), fonts],
            cwd=staged,
            capture_output=True,
            text=True,
            check=True,
        )
        capfd.readouterr()
        assert main(["fontcodesets", "--bdf-dir", str(staged / "bdf"), fonts]) == 0
        assert capfd.readouterr().out == perl.stdout, fonts

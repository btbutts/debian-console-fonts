# tools

Everything the build runs. Code taken from other projects keeps its licence notice in
the file headers.

## psf_font_maker

One Python package (standard library only, Python 3.12 or later; 3.12 is the oldest version
it is tested with) that replaces the Perl and C tools the build used. Run it from this directory's parent with
`PYTHONPATH=tools python3 -m psf_font_maker <tool> ...`; the Makefile does that.

```
psf_font_maker/
  main.py, __main__.py   the launcher: collects the tools below as sub-commands
  fonts/                 fonts          choose, convert and write whole sets of fonts (make fonts)
  common/                code several tools share (the PSF format, the error type)
  bdf2psf/               bdf2psf        BDF fonts -> PSF font
  fontcodesets/          fontcodesets   which code sets a font covers (+ codesets.toml data)
  otf2bdf/               otf2bdf        render a TrueType font to BDF with FreeType (freetype-py)
  freetype_lib/          freetype       find a FreeType that is new enough, or build one
  bdf_double/            bdf-double     enlarge a BDF by 2x
  compare_fonts/         compare-fonts  compare two directories of PSF fonts glyph by glyph
```

A tool's own files live in its package; only what two or more tools use goes in
`common/`. Each tool package has a `cli.py` with `NAME`, `HELP`, `declare` and `run`.

`bdf2psf` and `fontcodesets` are ports of console-setup 1.242~deb13u1's Perl scripts
(GPL-2.0-or-later, Copyright Anton Zinoviev; bdf2psf also contains code by Dimitar
Toshkov Zhekov) and produce byte-identical fonts. The Perl originals are kept in
`tests/reference/bdf2psf/` and `tests/reference/fontcodesets/` so the tests can keep proving that. `fontcodesets/codesets.toml`
is the symbol table from the Perl `fontcodesets`, as data.

`otf2bdf` is a port of otf2bdf 3.1 (C; Mark Leisher, New Mexico State University, MIT
licence, text in `otf2bdf/LICENSE`). It draws the glyphs with FreeType through
`freetype-py`, selecting and cropping them as the C tool did, and writes a leaner BDF
(the XLFD name and the properties bdf2psf reads; not the copyright and PostScript name
strings). Tested against the C tool: identical glyph tables for all four DejaVu Sans
Mono styles at the eight console sizes. It refuses a FreeType older than 2.13.3, which
hints some glyphs differently; the wheels of `freetype-py` bundle 2.13.2, so install it
against the system library: `pip install --no-binary freetype-py freetype-py`.
The original C sources are kept in `tests/reference/otf2bdf/` as a backup; nothing builds them.

`freetype` runs before `fonts` (the Makefile does it) and prints the directory of a FreeType
library that is 2.13.3 or later, for `fonts --freetype-lib-dir`. Versions are read from the
libraries themselves through `ctypes`, so `freetype-py` is not needed for this step. It
looks in the places listed in the top-level `README.md`, and if there is none builds
FreeType: it downloads the source named by the `freetype` entry of `sources.json` (checked against the
SHA-256 there) into that entry's `destination-path` directory and builds it there. Selection options
are the same as `fonts`, so that nothing is looked for or built when no selected font is
drawn from TrueType (`--always` overrides that). The renderer receives the directory through
the environment variable `PSF_FONT_MAKER_FREETYPE_DIR`, so that worker processes use it too.

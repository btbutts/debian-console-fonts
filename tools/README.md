# tools

Everything the build runs. Code taken from other projects keeps its licence notice in
the file headers.

## psf_font_maker

One Python package (standard library only, Python 3.11 or later) that replaces the Perl
and C tools the build used. Run it from this directory's parent with
`PYTHONPATH=tools python3 -m psf_font_maker <tool> ...`; the Makefile does that.

```
psf_font_maker/
  main.py, __main__.py   the launcher: collects the tools below as sub-commands
  common/                code several tools share (the PSF format, the error type)
  bdf2psf/               bdf2psf        BDF fonts -> PSF font
  fontcodesets/          fontcodesets   which code sets a font covers (+ codesets.toml data)
  otf2bdf/               otf2bdf        render a TrueType font to BDF with FreeType (freetype-py)
  bdf_double/            bdf-double     enlarge a BDF by 2x
  compare_fonts/         compare-fonts  compare two directories of PSF fonts glyph by glyph
  update_faces/          update-faces   regenerate mk/faces.mk from console-setup's Makefile
```

A tool's own files live in its package; only what two or more tools use goes in
`common/`. Each tool package has a `cli.py` with `NAME`, `HELP`, `declare` and `run`.

`bdf2psf` and `fontcodesets` are ports of console-setup 1.242~deb13u1's Perl scripts
(GPL-2.0-or-later, Copyright Anton Zinoviev; bdf2psf also contains code by Dimitar
Toshkov Zhekov) and produce byte-identical fonts. The Perl originals are kept in
`tests/reference/` so the tests can keep proving that. `fontcodesets/codesets.toml`
is the symbol table from the Perl `fontcodesets`, as data.

`otf2bdf` is a port of otf2bdf 3.1 (C; Mark Leisher, New Mexico State University, MIT
licence, text in `otf2bdf/LICENSE`). It draws the glyphs with FreeType through
`freetype-py`, selecting and cropping them as the C tool did, and writes a leaner BDF
(the XLFD name and the properties bdf2psf reads; not the copyright and PostScript name
strings). Tested against the C tool: identical glyph tables for all four DejaVu Sans
Mono styles at the eight console sizes. It refuses a FreeType older than 2.13.3, which
hints some glyphs differently; the wheels of `freetype-py` bundle 2.13.2, so install it
against the system library: `pip install --no-binary freetype-py freetype-py`.

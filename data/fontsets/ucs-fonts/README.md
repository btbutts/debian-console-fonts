# Unicode versions of the X11 "misc-fixed" fonts

By Markus Kuhn (<http://www.cl.cam.ac.uk/~mgk25/ucs-fonts.html>), README dated 2008-04-21. The
URL is in `sources.json`.

These are the X Window System bitmap fonts `-Misc-Fixed-*-*-*--*-*-*-*-C-*-ISO10646-1`:
Unicode (ISO 10646-1) extensions of the classic ISO 8859-1 X11 terminal fonts used by xterm,
emacs and many other applications.

## What is here

Nine fonts: `7x14`, `7x14B`, `8x13`, `8x13B`, `8x13O`, `9x15`, `9x15B`, `9x18` and `9x18B`.

No font covers Unicode completely. The target character repertoires were: TARGET1, 617
characters (ISO 8859 parts 1-5, 7-10 and 13-16, CEN MES-1, ISO 6937, CP1251/CP1252, VT100
graphics) for small bold, italic and proportional fonts; TARGET2, 886 characters (adds the
Windows Glyph List 4, mathematical characters and some combining characters) for normal fixed
fonts; and TARGET3, 3282 characters (adds all European scripts, phonetic symbols, many
mathematical symbols, typographic punctuation, box drawing, control code pictures and graphical
shapes). Status of the fonts kept here: 8x13 and 9x15 and 9x18 reach TARGET3; 7x14 reaches
TARGET2; 7x14B, 8x13B, 9x15B and 9x18B reach TARGET1; 8x13O reaches TARGET1 without Hebrew and
block graphics. None contains a character with the Unicode East Asian Width property W or F.

## How this project uses it

`psf_font_maker` takes `8x13`, `8x13B`, `8x13O`, `7x14`, `7x14B`, `9x15`, `9x15B`, `9x18` and
`9x18B` for the `Fixed*` console fonts, as the main source of their glyphs.

## What upstream also ships and is not kept here

The other fixed fonts (`4x6`, `5x7`, `5x8`, `6x9`, `6x10`, `6x12`, `6x13` and variants,
`7x13` and variants, `10x20`), which this project does not use, and two files that are not in
the public domain, `helvR12.bdf` (Adobe Systems and Digital Equipment Corporation) and
`clR6x12.bdf` (Dale Schumacher and Robert Brady).

# UNI-VGA

UNI-VGA by Dmitry Bolkhovityanov: a Unicode 8x16 VGA font for X11 and the console. Version
25112000 (25 November 2000; the font file is dated 2001). Downloaded from the author's page,
<https://www.inp.nsk.su/~bolkhov/files/fonts/univga/>; the URL is in `sources.json`.

The author describes it as primarily intended to be the single source of fonts for the
console and for XDosEmu.

## What is here

Only `u_vga16.bdf`: 2899 glyphs, 8x16, XLFD name
`-Bolkhov-VGA-Medium-R-Normal--16-160-75-75-C-80-iso10646-1`. The font notes that VGA is a
trademark of IBM Corporation.

## How this project uses it

`VGA16` is this font alone, for every code set, and `VGA32x16` is the same font enlarged
twofold.

## What upstream also ships and is not kept here

A converter (`bdf2psf.pl`), a `Makefile`, three encoding tables (`AsianCyr.sfm`, `UniCyrX.sfm`,
`WinCyr.sfm`) used to make single-encoding fonts, and the `uni-vga.lsm` catalogue entry. This
project does not use them.

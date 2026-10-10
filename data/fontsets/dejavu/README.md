# DejaVu fonts

DejaVu fonts 2.37, (c) 2004-2016 the DejaVu fonts team. Downloaded from SourceForge
(<https://dejavu-fonts.github.io/>, <http://dejavu.sourceforge.net/>); the exact URL and
version are in `sources.json`.

The DejaVu fonts are a family based on the Bitstream Vera Fonts (version 1.10,
<http://gnome.org/fonts/>). Their purpose is to provide a wider range of characters while
keeping the original look and feel.

## What is here

The twenty-two TrueType files in `ttf/`:

| Family | Files |
|---|---|
| DejaVu Sans Mono | `DejaVuSansMono.ttf`, `-Bold`, `-Oblique`, `-BoldOblique` |
| DejaVu Sans | `DejaVuSans.ttf`, `-Bold`, `-Oblique`, `-BoldOblique`, `-ExtraLight` (experimental) |
| DejaVu Sans Condensed (experimental) | `DejaVuSansCondensed.ttf`, `-Bold`, `-Oblique`, `-BoldOblique` |
| DejaVu Serif | `DejaVuSerif.ttf`, `-Bold`; `-Italic`, `-BoldItalic` (experimental) |
| DejaVu Serif Condensed (experimental) | `DejaVuSerifCondensed.ttf`, `-Bold`, `-Italic`, `-BoldItalic` |
| DejaVu Math TeX Gyre | `DejaVuMathTeXGyre.ttf` |

Some characters come from the Arev fonts (Copyright (c) 2006 Tavmjong Bah): U+01BA, U+01BF,
U+01F7, U+021C-U+021D, U+0220, U+0222-U+0223, U+02B9, U+02BA, U+02BD, U+02C2-U+02C5,
U+02D4-U+02D5, U+02D7, U+02EC-U+02EE, U+0346-U+034E, U+0360, U+0362, U+03E2-03EF,
U+0460-0463, U+0466-U+0486, U+0488-U+0489, U+04A8-U+04A9, U+0500-U+050F, U+2055-205E,
U+20B0, U+20B2-U+20B3, U+2102, U+210D, U+210F, U+2111, U+2113, U+2115, U+2118-U+211A,
U+211C-U+211D, U+2124, U+2135, U+213C-U+2140, U+2295-U+2298, U+2308-U+230B, U+26A2-U+26B1,
U+2701-U+2704, U+2706-U+2709, U+270C-U+274B, U+2758-U+275A, U+2761-U+2775, U+2780-U+2794,
U+2798-U+27AF, U+27B1-U+27BE, U+FB05-U+FB06. DejaVu Math TeX Gyre is TeX Gyre DJV Math by
B. Jackowski, P. Strzelczyk and P. Pianowski on behalf of the TeX users groups.

## How this project uses it

`psf_font_maker` renders the DejaVu Sans Mono faces (and, on request, the others) with
FreeType to make the `DejaVu*` console fonts. Upstream publishes the fonts in source form (as
FontForge SFD files) and as these TTF files; only the TTF files are kept.

## What upstream also ships and is not kept here

The SFD sources, the LGC-only derivative fonts, the fontconfig files, the coverage lists and
the news and bug lists.

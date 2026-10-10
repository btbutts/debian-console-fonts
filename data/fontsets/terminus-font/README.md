# Terminus Font

Terminus Font 4.49.1 by Dimitar Toshkov Zhekov. Downloaded from SourceForge
(<https://sourceforge.net/projects/terminus-font/>); the exact URL and version are in
`sources.json`.

## What is here

Only the twenty `ter-u*.bdf` files, the font itself. Terminus is a clean, fixed-width bitmap
font designed for long sessions at the console.

| | |
|---|---|
| Sizes | 6x12, 8x14, 8x16, 10x18, 10x20, 11x22, 12x24, 14x28, 16x32 |
| Weights | normal, bold, CRT VGA bold |
| Characters | 1356, covering about 120 language sets |
| Code pages | ISO 8859-1/2/5/7/9/13/15/16, Paratype PT154/PT254, KOI8-R/U/E/F, Esperanto, many IBM, Windows and Macintosh code pages, and the IBM VGA, vt100 and xterm pseudographic characters |
| Format | Bitmap Distribution Format (BDF) version 2.1 |

The file names are `ter-u<SIZE><STYLE>.bdf`. `<SIZE>` is the font height. `<STYLE>` is `n` for
normal (all sizes), `b` for bold (all sizes except 6x12, where there is no room for a bold
font) and `v` for CRT VGA bold (8x14 and 8x16 only; it uses the eighth column of the
character matrix).

## Notes from the author that matter when using the fonts

- Some characters exist in two variants. These files have the default variants. The default
  for Unicode range 2800-28FF is oriented towards pseudographics, and the font does not
  support Braille in any way.
- The sizes 6x12, 11x22, 14x28 bold and 16x32 normal are worse than the others.
- 210E and 210F are not italic. 226A, 226B and the double-struck letters are not very good.
  2135 may be wrong. The Hebrew letters and sheqel are uppercase height, which compensates
  for the missing width.
- There is no italic version and no scalable version.

## How this project uses it

`psf_font_maker` converts these BDF files into the `Terminus*` console fonts
(`Uni2-Terminus16` and so on). They replace the older copy that Debian's console-setup
bundles.

## What upstream also ships and is not kept here

The build scripts (`configure`, `Makefile`, `bin/`, `win32/`), the character maps (`uni/`,
`dup`), the patches for the alternative character variants (`alt/`), the fontconfig file and
the change logs. This project does not use them.

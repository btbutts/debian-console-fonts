# otf2bdf 3.1 (C sources) and the headers they include

**For information only.** Nothing in this project compiles or runs these files, and
`tools/psf_font_maker` does not use them. `psf_font_maker`'s `otf2bdf` module is a Python port of this
program, and these files are kept as a record of the code it was written from.

## The program

`otf2bdf.c`, `remap.c` and `remap.h` are the unmodified source files of otf2bdf 3.1 by Mark
Leisher, Department of Mathematical Sciences, New Mexico State University, from
<https://github.com/jirutka/otf2bdf/archive/refs/tags/v3.1.tar.gz> (SHA-256
`5842a6c604a8aa747f9f49838e3a91ce587c8568681300bc70418aeebd7ecc43`). Its licence is in the
header of each file (also in `tools/psf_font_maker/otf2bdf/LICENSE`). The upstream build files, character maps and manual
are not kept.

## FreeType headers

`otf2bdf.c` includes `ft2build.h` and the `FT_GLYPH_H`, `FT_SFNT_NAMES_H` and
`FT_TRUETYPE_TABLES_H` headers. This directory holds those and every header they include in turn,
copied unmodified from the `include/` directory of FreeType 2.14.3
(<https://download.savannah.gnu.org/releases/freetype/freetype-2.14.3.tar.gz>): `ft2build.h`
and `freetype/` (19 files). The layout is the one a compiler expects, so `-I` this directory finds them.

FreeType is distributed under two licences, of which you choose one: the FreeType License
(`freetype-license/FTL.TXT`) or the GNU General Public License version 2 or later (the text is in
section 4 of the top-level `LICENSE`, and at <https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>).
`freetype-license/LICENSE.TXT` is FreeType's own statement of this. Upstream:
<https://freetype.org> and <https://gitlab.freedesktop.org/freetype/freetype>.

## Headers not kept

`stdio.h`, `stdlib.h`, `string.h` and `unistd.h` belong to the C library and the operating system
of whoever compiles, and differ between them; `windows.h` (included by `remap.c` on Windows only) is
part of Microsoft's Windows SDK, which may not be redistributed. None of them is a part of otf2bdf.

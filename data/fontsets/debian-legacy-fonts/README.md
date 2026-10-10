# debian-legacy-fonts

The BDF fonts for which this project has not found another source, so it keeps them itself. They are copies of files from Debian's console-setup 1.242~deb13u1
(`Fonts/bdf/`) and are used exactly as they were there. Fonts that do have an upstream
release are downloaded into their own directories next to this one (see `sources.json`).

| Files | What they are |
|---|---|
| `legacy8*`, `legacy10*`, `legacy12*`, `legacy14*`, `legacy19*` (and `legacy14*-double`) | The VGA faces' fonts for each code set. Debian generated them automatically from the Linux console fonts of the `console-data` package. Several are merges of two to four of those fonts. The `-double` files are twofold enlargements. |
| `7x14-IL2`, `8x13-IL2`, `9x15-IL2`, `…B-IL2` and the `…c` files (`7x14c`, `8x13c`, `9x15c`, `8x13Bc`, `9x15Bc`) | Variants of the X11 "misc-fixed" fonts: ISO 8859-2 versions re-encoded to Unicode (`-IL2`) and the extra upper-half glyphs (`c`). |
| `8x16-IL2`, `8x16c` | The 8x16 font of Sony, in the same two variants. |
| `h14*`, `h16*`, `h24*` | /efont/ fonts (The Electronic Font Open Laboratory). |
| `etl14-unicode`, `etl16-unicode`, `etl24-unicode` | ETL fonts. |
| `unifont.bdf` | GNU Unifont, an old snapshot. |
| `georgian14`, `georgian16` | Georgian fonts. |
| `Goha*`, `GohaClassic*` | The Ethiopic fonts donated by Yitna Firdyiwek. |
| `75dpi-*`, `100dpi-*` | Courier and Lucida Typewriter from the X11 distribution, with `-IL2` re-encodings. |

The licences differ from file to file: see `LICENSE.md`. `AUTHORS.md` credits the authors.

The aim is to replace these with fonts built from their real upstreams where one exists
(the Linux console fonts for `legacy*`, the Efont, ETL, Unifont and Georgian releases). Which
of them a face uses is in `data/faces.toml`.

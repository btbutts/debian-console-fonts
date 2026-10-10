# data

The tables and fonts the build reads. They belong to this project.

| Path | What it is |
|---|---|
| `faces.toml` | The faces, which BDF fonts make each, and the code sets each is made for. Edited by hand. |
| `codesets/` | For each code set, the symbols it needs, in priority order; the extension of the file (`.256`, `.512`) is the number of positions in the font. |
| `standard.equivalents`, `arabic.equivalents` | Lists of symbols that can share one glyph (for example Latin A and Greek Alpha). |
| `ascii.set`, `linux.set`, `useful.set` | Symbol lists that every font includes first. |
| `fontsets/` | The fonts, one directory per source: `terminus-font`, `ucs-fonts`, `uni-vga`, `dejavu` (downloaded; the directory of each is its `destination-path` in `sources.json`) and `debian-legacy-fonts` (the ones we have not found another source for). Each has its own `README.md`, `AUTHORS.md` and `LICENSE.md`. |

`codesets/`, the `.equivalents` files and the `.set` files are copies of files in Debian's
console-setup 1.242~deb13u1 (`Fonts/`; there the code set lists are in `Fonts/fontsets/`).
`faces.toml` began as the data of console-setup's `Fonts/Makefile`. The symbols that decide which
code sets a font covers (`tools/psf_font_maker/fontcodesets/codesets.toml`) come from
console-setup's `fontcodesets` in the same way. See `LICENSE.md` and `AUTHORS.md`.

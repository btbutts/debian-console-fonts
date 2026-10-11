# debian-console-fonts

Linux console (PSF) fonts, named and laid out the way Debian's `console-setup` names and
lays them out, built from the fonts' original sources. Not specific to any distribution
or build system: unpack a release tarball on Linux and run `make`.

## How it is organised

| Path | Purpose |
|---|---|
| `Makefile` | The front door: `make list`, `make fonts`, `make install`. It only passes your choices on to the Python tool. |
| `tools/psf_font_maker/` | The Python tool that does all the work. One package with a sub-package per tool; see [`tools/README.md`](tools/README.md). |
| `data/` | Everything the tool reads: the face list, the code set symbol lists, the equivalents and symbol sets, and the fonts. [`data/README.md`](data/README.md) |
| `data/fontsets/<name>/` | One directory per font source: `terminus-font`, `ucs-fonts`, `uni-vga`, `dejavu` (downloaded) and `debian-legacy-fonts` (kept here because no other source has been found). Each has a `README.md`, an `AUTHORS.md` and a `LICENSE.md`. |
| `sources.json` | The only place source URLs, versions and target directories (`destination-path`) are declared; the downloader puts the files there and `psf_font_maker` looks for them there. `"enabled": false` switches an entry off; `"download": false` keeps the downloader from fetching it (see below). |
| `data/fontsets/sources.lock.json` | Resolved URL, version and archive SHA-256 of every source. |
| `.github/` | The downloader and the `download-sources` workflow that runs it monthly, on demand, and whenever `sources.json` changes. |
| `tests/` | `pytest` suites for the downloader and the tools. A few tests compare with the Perl originals in `tests/reference/` (which also keeps the C sources of otf2bdf as a backup), and a few more with Debian's console-setup if you enable it in `sources.json` and download it (they skip otherwise). |

## Sources

| Name | What it provides | Where from |
|---|---|---|
| `terminus-font` | Terminus by Dimitar Toshkov Zhekov (SIL OFL 1.1): the `ter-u*.bdf` files | SourceForge |
| `ucs-fonts` | Nine of the Unicode "misc-fixed" fonts by Markus Kuhn (public domain) | cl.cam.ac.uk |
| `uni-vga` | UniVGA by Dmitry Bolkhovityanov: `u_vga16.bdf`, the source of VGA16 and VGA32x16 | inp.nsk.su |
| `dejavu` | All 22 DejaVu TrueType files (Bitstream Vera licence) | SourceForge |

The downloader puts each font source into the `destination-path` of its entry in `sources.json` (`data/fontsets/<name>/`), keeps only the files listed under
`matched-fonts` in `sources.json`, and leaves the `README.md`, `AUTHORS.md` and `LICENSE.md` of that
directory (our own, listed under `keep-files`) untouched when it updates the tree.

`data/fontsets/debian-legacy-fonts/` holds the BDF fonts for which no other source has been
found (the VGA faces' `legacy*` fonts, Efont, ETL, Unifont, Georgian, Goha, Courier and Lucida
Typewriter, and the `-IL2` variants). They are copies from Debian's console-setup; nothing is
read from console-setup any more.

`sources.json` also has two entries marked `"download": false`, which the downloader does not
fetch but `psf_font_maker` reads: `debian-legacy-fonts` (kept in the repository by hand, so it
has only a `destination-path`) and `freetype` (fetched by the font build when needed, described above).
It also lists sources that are switched off with `"is-in-use": false`, which the
downloader skips: `console-setup` (Debian's package, which the tables and the legacy fonts were
copied from; downloading it into `sources/console-setup` lets a few tests compare this project's
output with its own Makefile), and `otf2bdf` and `ttf2psf` (the C tools that `psf_font_maker`
replaced or was compared with). Set the flag to `true` and run the downloader to fetch one.

The downloader unpacks each archive to a temporary place and compares the files with what is
already in `data/fontsets/`. If they are identical it writes nothing and leaves the lock file
alone, so a repackaged upstream archive causes no change and no commit.

## Building fonts

Needs GNU make, python3 (3.12 or later; 3.12 is the oldest version it is tested with) and the
fonts in `data/fontsets/` (a release tarball already has them; otherwise run the downloader).
Making the fonts needs no network access, except to fetch FreeType in the one case described
next.

DejaVu is drawn from its TrueType files with FreeType 2.13.3 or later (older versions hint some
glyphs differently), through the `freetype-py` Python package. Before it makes any fonts the tool
writes down what you asked for and checks what that needs (the `==> Requirements` part of its
log): where `freetype-py` is, looking through the import path of the Python that runs it (a
Buildroot host tree, a virtual environment or the system's `python3-freetype` are all found),
and which FreeType it will use. Each place looked at is written on the log, and a missing
requirement stops the build before any font is made. Nothing of this happens unless a selected
font is drawn from TrueType. The FreeType is chosen like this:

1. `FREETYPE_LIB_DIR`, if you set it (you never have to), must hold one;
2. otherwise one built earlier in `build/freetype/` is used;
3. otherwise one in a Buildroot host tree (`$HOST_DIR`, which Buildroot exports to its packages,
   or the prefix of the running Python, which is `$(HOST_DIR)` for Buildroot's host Python);
4. otherwise one on the system (`LD_LIBRARY_PATH`, `/usr/lib` and its multiarch directories,
   `/usr/local/lib`, Homebrew and MacPorts);
5. otherwise FreeType's source is downloaded and built. The `freetype` entry of `sources.json`
   gives the URL (GNU's `download.savannah.gnu.org`), the version, the SHA-256 that the
   download must have and the directory to work in (`build/freetype/`); it is marked
   `"download": false`, so the dependency downloader does not fetch it and it is not kept in
   this repository. It is built with `./configure && make && make install` (about ten
   seconds), which needs network access and a C compiler (GCC or Clang); without a compiler you
   are told to install one. An archive already in `FREETYPE_ARCHIVE_DIR`, if you set it, or in
   `build/freetype/` is used instead of downloading. Whichever is used must have the
   SHA-256 recorded in `sources.json`, because `configure` from it is run on your machine; a
   re-released tarball needs that hash updated deliberately. Windows cannot build it: give `FREETYPE_LIB_DIR`.

The library chosen is the one used, whatever else is installed; the last line of the
requirements, `check: freetype-py loads FreeType ...`, says which one `freetype-py` really
loaded. `make freetype` does only the FreeType step. `freetype-py` itself
must be installed from source so that it uses a separate library rather than its own bundled
(older) FreeType: `pip install --no-binary freetype-py freetype-py`. To build without DejaVu,
leave it out of `FACES`.

```sh
make list                     # what would be built (default: 124 fonts)
make fonts                    # build into out/*.psf.gz
make fonts FACES="Terminus% VGA%" CODESETS="Uni2 Lat15" OUT=/tmp/fonts
make install DESTDIR=/target  # build into /target/usr/share/consolefonts
make freetype                 # only find or build the FreeType that DejaVu needs
make distclean                # remove out/ and the FreeType that was built
make help
```

The Makefile passes the choices to `python3 -m psf_font_maker fonts`. An option you leave
out has the tool's default; an option you set to nothing is an error, never the default.

| Option | Meaning | Default |
|---|---|---|
| `FACES` | patterns for `<Face><size>` (one `%` each), e.g. `Terminus%`, `DejaVuBold%` | `Terminus% VGA% DejaVu% Fixed%` |
| `CODESETS` | `Uni1 Uni2 Uni3 Lat15 Lat2 Lat7 Lat38 Greek Hebrew Arabic CyrSlav CyrKoi CyrAsia Vietnamese Armenian Georgian Ethiopian Lao Thai` and the `Full*` screen-reader variants | `Uni1 Uni2 Uni3` |
| `SKIP` | `<Face><size>` patterns to leave out, e.g. `TerminusBoldVGA16` | none |
| `POOL` | `good` (the faces offered by default) or `all` | `good` |
| `DEJAVU_SIZES` | cell widths to render DejaVu at; the height follows from the font | `16 20 24 28 32 40 48 64` |
| `DEJAVU_PROPORTIONAL` | non-empty adds the 18 proportional DejaVu faces (`DejaVuSans*`, `DejaVuSerif*`, `DejaVuMath`); glyphs wider than the cell are dropped | off |
| `JOBS` | processes to use | one per CPU |
| `QUIET` | set to `1` to say less while the fonts are made: a line per family and code set, and a heartbeat when nothing else is said. The configuration, every check of the build environment, the stages and the warnings are always written | each face and the percentage are written too |
| `VERBOSE` | set to `1` to say more while the fonts are made: each font as it is written and every conversion warning | a summary of the warnings by kind |
| `FREETYPE_LIB_DIR` | directory holding the `libfreetype` to render DejaVu with; it is an error if it holds none that is 2.13.3 or later | looked for, then built |
| `FREETYPE_ARCHIVE_DIR` | a directory that may already hold the FreeType source archive (a package manager's download directory); if it does, that file is used and nothing is downloaded. Its checksum must match | none |
| `SOURCES` | the manifest that says where each source is | `sources.json` |
| `DATA` | where the tables and fonts are | `data` |
| `OUT` | where `make fonts` writes | `out` |
| `DESTDIR`, `PREFIX`, `FONTDIR` | where `make install` writes: `$(DESTDIR)$(FONTDIR)` | `FONTDIR=$(PREFIX)/share/consolefonts`, `PREFIX=/usr` |

Fonts are named as console-setup names them: `<Codeset>-<Face><height>[x<width>]`, for
example `Uni2-Terminus20x10.psf.gz` or `Lat15-Fixed16.psf.gz`. Which code sets a face
covers is computed from its BDF fonts by `fontcodesets`.

Only the finished `.psf.gz` files are written, and only into the directory you name.
That is how a package such as a Buildroot one uses it: it passes its selection as `FACES`
and `CODESETS` and its target directory as `DESTDIR`.

DejaVu Sans Mono comes in four styles: `DejaVu` and `DejaVuBold` (named and sized exactly
as Debian's, and identical to its fonts) plus `DejaVuOblique` and `DejaVuBoldOblique`.
Each is rendered at a cell width of N pixels and converted like every other face.

VGA16 is Uni-VGA's `u_vga16.bdf` alone and VGA32x16 is its 2x pixel enlargement. They
differ from Debian's by under 0.2% of glyphs for the non-Arabic code sets; for Arabic
(in `Uni1`) Debian replaces about 140 glyphs with ones from another project, which are
not used here. Uni-VGA has no 8 or 14 row font, so VGA8, VGA14 and VGA28x16 use the
`legacy*.bdf` files in `data/fontsets/debian-legacy-fonts/`.

The conversion is a Python port of console-setup's `bdf2psf`; given the same BDF fonts it
writes the same bytes as the Perl original, which is checked by the tests. The Terminus
fonts differ from Debian's package by about 0.6% of glyphs (the 4.49.1 release against
Debian's 2019 copy) and the Fixed fonts by about 0.05% (misc-fixed from `ucs-fonts`
against Debian's copy).

## Changing a source

Edit `sources.json`. To move to a new release change the entry's `version`: the URL is
rebuilt from it (`{version}`, `{major}`, `{minor}`, `{patch}`, `{major_minor}`), the new
archive is downloaded and the old tree under `destination-path` is replaced. The Action does this on
push; locally:

```sh
python3 -m venv .venv && .venv/bin/pip install requests truststore pytest
.venv/bin/pip install --no-binary freetype-py freetype-py   # for the DejaVu tests
.venv/bin/python .github/actions-scripts/dependencyDownloader.py --sources sources.json
PYTHONPATH=tools .venv/bin/python -m pytest
```

The `sha256` of an entry is the SHA-256 of the archive as last installed; it says whether the
archive changed, not whether it is intact (upstream sometimes re-releases a tarball). The
downloader fetches every archive each run: one with that SHA-256 is the same file, so nothing
is done. Any other is unpacked and compared with the installed files; if they differ the files
are replaced and the new SHA-256 is written into `sources.json`, and if they are identical
nothing is written at all.

`--only NAME` limits a run to named entries and `--force` re-extracts even when the lock
matches. Entry keys are documented at the top of `.github/actions-scripts/sources_manifest.py`.

## Licences

The build recipe and tooling are GPL-2.0-or-later; the dependency downloader is MIT. Every
directory of fonts in `data/fontsets/` keeps its own licence (in its `LICENSE.md`), and the generated
fonts carry the licences of the fonts they are built from. [`LICENSE`](LICENSE) has the
details and points to the full text of each licence.

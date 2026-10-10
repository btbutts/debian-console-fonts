# debian-console-fonts

Linux console (PSF) fonts built the way Debian's `console-setup` builds them,
from the fonts' original upstream sources. Not specific to any distribution or
build system: unpack a release tarball on Linux and run `make`.


## How it is organised

| Path | Purpose |
|---|---|
| `sources.json` | The only place source URLs and versions are declared. |
| `sources/<name>/` | Extracted upstream trees, written by the downloader and committed by the `download-sources` Action. |
| `sources/sources.lock.json` | Resolved URL, version and archive SHA-256 of every source. |
| `.github/actions-scripts/dependencyDownloader.py` | Downloads and unpacks the sources (`--sources sources.json`). |
| `.github/workflows/download-sources.yml` | Runs the downloader monthly, on demand, and whenever `sources.json` changes. |
| `Makefile`, `mk/faces.mk`, `mk/dejavu.mk` | The build recipe. `mk/faces.mk` is generated from console-setup's Makefile by `update-faces`; `mk/dejavu.mk` renders DejaVu from its TTFs. |
| `tools/` | The programs the build runs. `tools/psf_font_maker/` is one Python package with a sub-package per tool (`bdf2psf`, `fontcodesets`, `otf2bdf`, `bdf_double`, `compare_fonts`, `update_faces`) and a `common/` for what they share; `otf2bdf` renders TrueType fonts through `freetype-py`. Origins and licences: [`tools/README.md`](tools/README.md). |
| `tests/` | `pytest` suites for the downloader (no network needed) and the Makefile and tools (needs `sources/` and `make`; a few tests also compare with the Perl originals and need `perl`). |

## Sources

| Name | What it provides | Where from |
|---|---|---|
| `console-setup` | fontsets, equivalents, symbol sets, Debian's own BDFs (legacy VGA supplements, ISO 8859-2 variants, Efont, ETL, Georgian, GNU Unifont, pre-rendered DejaVu) | Debian |
| `terminus-font` | Terminus by Dimitar Toshkov Zhekov (SIL OFL 1.1) | SourceForge |
| `ucs-fonts` | Unicode "misc-fixed" fonts by Markus Kuhn (public domain) | cl.cam.ac.uk |
| `uni-vga` | UniVGA by Dmitry Bolkhovityanov: `u_vga16.bdf`, the source of VGA16 and VGA32x16 | inp.nsk.su |
| `dejavu` | All 22 DejaVu TrueType files (Bitstream Vera licence) | SourceForge |

## Building fonts

Needs GNU make, gzip and python3 (3.11 or later), and a populated `sources/` (a release
tarball already has it). DejaVu is rendered from its TrueType files, which also needs
the `freetype-py` package built against a system FreeType of version 2.13.3 or later
(`pip install --no-binary freetype-py freetype-py`; the prebuilt wheels bundle an older
FreeType, which the tool refuses). Without it use `USE_UPSTREAM="terminus-font uni-vga
ucs-fonts"` to take Debian's pre-rendered DejaVu BDFs instead. No network access.

```sh
make list                     # what would be built (default: 124 fonts)
make fonts                    # build into out/*.psf.gz
make fonts FACES="Terminus% VGA%" CODESETS="Uni2 Lat15" OUT=/tmp/fonts
make help
```

| Option | Meaning | Default |
|---|---|---|
| `FACES` | patterns for `<Face><size>` (one `%` each), e.g. `Terminus%`, `DejaVuBold%` | `Terminus% VGA% DejaVu% Fixed%` |
| `CODESETS` | console-setup code sets: `Uni1 Uni2 Uni3 Lat15 Lat2 Lat7 Lat38 Greek Hebrew Arabic CyrSlav CyrKoi CyrAsia Vietnamese Armenian Georgian Ethiopian Lao Thai` and the `Full*` screen-reader variants | `Uni1 Uni2 Uni3` |
| `SKIP` | `<Face><size>` patterns to leave out, e.g. `TerminusBoldVGA16` | none |
| `POOL` | `good` (console-setup's default faces) or `all` | `good` |
| `USE_UPSTREAM` | sources whose BDFs replace console-setup's bundled copies (`terminus-font`, `uni-vga`, `ucs-fonts`, `dejavu`) | `terminus-font uni-vga ucs-fonts dejavu` |
| `DEJAVU_SIZES` | cell widths to render DejaVu at; the height follows from the font | `16 20 24 28 32 40 48 64` |
| `DEJAVU_PROPORTIONAL` | non-empty adds the 18 proportional DejaVu faces (`DejaVuSans*`, `DejaVuSerif*`, `DejaVuMath`); glyphs wider than the cell are dropped | off |

Fonts are named exactly as console-setup names them: `<Codeset>-<Face><height>[x<width>]`,
for example `Uni2-Terminus20x10.psf.gz` or `Lat15-Fixed16.psf.gz`. Which code sets a
face covers is computed from its BDFs by `fontcodesets` (a port of console-setup's).

DejaVu Sans Mono comes in four styles: `DejaVu` and `DejaVuBold` (named and sized
exactly as Debian's, and identical to its fonts) plus `DejaVuOblique` and
`DejaVuBoldOblique`. Each is rendered with `otf2bdf -c C -p <width> -r 115`
and converted by `bdf2psf` like every other face.

VGA16 is Uni-VGA's `u_vga16.bdf` alone and VGA32x16 is its 2x pixel enlargement
(`bdf-double`, which reproduces console-setup's `u_vga16-double.bdf`
exactly). They differ from Debian's by under 0.2% of glyphs for the non-Arabic
code sets; for Arabic (in `Uni1`) Debian replaces about 140 glyphs with ones from
another project, which are not used here. Uni-VGA has no 8 or 14 row font, so
VGA8, VGA14 and VGA28x16 still use console-setup's `legacy*.bdf`.

The recipe is console-setup's, with a Python port of its `bdf2psf` that gives the same bytes. Built from
console-setup's own BDFs the output is byte-identical to console-setup's
Makefile (`USE_UPSTREAM=`; tested). With the defaults the Terminus
fonts differ from Debian's package by about 0.6% of glyphs (the 4.49.1 release
against Debian's 2019 copy) and the Fixed fonts by about 0.05% (misc-fixed from
`ucs-fonts` against Debian's copy). Uni-VGA's `u_vga16.bdf` is byte-identical.

## Changing a source

Edit `sources.json`. To move to a new release change the entry's `version`: the
URL is rebuilt from it (`{version}`, `{major}`, `{minor}`, `{patch}`,
`{major_minor}`), the new archive is downloaded and the old tree under `dest` is
replaced. The Action does this on push; locally:

```sh
python3 -m venv .venv && .venv/bin/pip install requests truststore pytest
.venv/bin/python .github/actions-scripts/dependencyDownloader.py --sources sources.json
.venv/bin/python -m pytest
```

`--only NAME` limits a run to named entries and `--force` re-extracts even when
the lock matches. Entry keys are documented at the top of the script.

## Licences

The build recipe and tooling are GPL-2.0-or-later; the dependency downloader is
MIT. Every source under `sources/` keeps its own licence, and the generated
fonts carry the licences of the fonts they are built from. [`LICENSE`](LICENSE)
has the details and points to the full text of each licence.

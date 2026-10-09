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
| `Makefile`, `mk/faces.mk` | The build recipe. `mk/faces.mk` is generated from console-setup's Makefile by `tools/update-faces.py`. |
| `tools/` | `update-faces.py` (regenerates `mk/faces.mk`) and `compare-fonts.py` (per-code-point font comparison). |
| `tests/` | `pytest` suites for the downloader (no network needed) and the Makefile (needs `sources/`, `make`, `perl`). |

## Sources

| Name | What it provides | Where from |
|---|---|---|
| `console-setup` | `bdf2psf`, fontsets, equivalents, symbol sets, Debian's own BDFs (legacy VGA supplements, ISO 8859-2 variants, Efont, ETL, Georgian, GNU Unifont, pre-rendered DejaVu) | Debian |
| `terminus-font` | Terminus by Dimitar Toshkov Zhekov (SIL OFL 1.1) | SourceForge |
| `ucs-fonts` | Unicode "misc-fixed" fonts by Markus Kuhn (public domain) | cl.cam.ac.uk |
| `uni-vga` | UniVGA by Dmitry Bolkhovityanov | inp.nsk.su |
| `dejavu` | DejaVu Sans Mono TrueType (Bitstream Vera licence) | SourceForge |
| `ttf2psf`, `otf2bdf` | Optional converters, disabled until needed | GitHub |

## Building fonts

Needs GNU make, perl and gzip, and a populated `sources/` (a release tarball
already has it). No network access.

```sh
make list                     # what would be built (default: 92 fonts)
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
| `USE_UPSTREAM` | sources whose BDFs replace console-setup's bundled copies (`terminus-font`, `uni-vga`, `ucs-fonts`) | `terminus-font uni-vga` |

Fonts are named exactly as console-setup names them: `<Codeset>-<Face><height>[x<width>]`,
for example `Uni2-Terminus20x10.psf.gz` or `Lat15-Fixed16.psf.gz`. Which code sets a
face covers is computed from its BDFs with console-setup's `fontcodesets`.

The recipe is console-setup's: the same `bdf2psf` and arguments. Built from
console-setup's own BDFs the output is byte-identical to console-setup's
Makefile (`USE_UPSTREAM=`; tested). With the defaults, only the Terminus fonts
differ from Debian's package, by about 0.6% of glyphs (the 4.49.1 release against
Debian's 2019 copy).

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

Each component keeps its own licence (see the files under `sources/` and the
table above). The repository-level licence has not been chosen yet.

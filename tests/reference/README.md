# Reference originals

Unmodified copies of the programs that `tools/psf_font_maker` replaced. They are kept so the
tests can compare against them, and as a backup of the code the port was made from.

| Directory | What | Origin | Licence |
|---|---|---|---|
| `bdf2psf/` | `bdf2psf`, Perl | Debian console-setup 1.242~deb13u1 (`Fonts/bdf2psf`) | GPL-2.0-or-later, Anton Zinoviev; also code by Dimitar Toshkov Zhekov |
| `fontcodesets/` | `fontcodesets`, Perl | Debian console-setup 1.242~deb13u1 (`Fonts/fontcodesets`) | GPL-2.0-or-later, Anton Zinoviev |
| `otf2bdf/` | `otf2bdf.c`, `remap.c`, `remap.h`, C, and the FreeType headers they include (see its `README.md`) | otf2bdf 3.1, <https://github.com/jirutka/otf2bdf/archive/refs/tags/v3.1.tar.gz> (SHA-256 `5842a6c604a8aa747f9f49838e3a91ce587c8568681300bc70418aeebd7ecc43`) | MIT-style licence in the file headers, Department of Mathematical Sciences, New Mexico State University |

The Perl scripts are run by `tests/test_psf_font_maker.py`. The C sources are not built or run
by anything here; only the three source files of the tool and the FreeType headers they
include are kept, not its build files, maps or manual.

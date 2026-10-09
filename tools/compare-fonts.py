#!/usr/bin/env python3
"""Compare PSF console fonts glyph by glyph, keyed by Unicode code point.

    compare-fonts.py DIR_A DIR_B [--glob '*Terminus*'] [--min-identical 99.0]

Fonts with the same file name in both directories are compared (.psf and
.psf.gz are both read). For each code point present in both, the glyph bitmaps
are compared, so differences in glyph order or in how many code points share a
glyph do not count. Prints one line per font and a total; exits 1 if the share
of identical glyphs falls below --min-identical (default 0, never fails).
"""

from __future__ import annotations

import argparse
import fnmatch
import gzip
import struct
import sys
from pathlib import Path

PSF1_MAGIC = b"\x36\x04"
PSF2_MAGIC = b"\x72\xb5\x4a\x86"


def _open(path: Path) -> bytes:
    data = path.read_bytes()
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def load_psf(path: Path) -> tuple[int, int, dict[int, bytes]]:
    """Return (width, height, {code point: bitmap}) for a PSF1 or PSF2 font."""
    data = _open(path)
    glyphs: list[bytes]
    unicode_table = b""
    if data[:2] == PSF1_MAGIC:
        mode, size = data[2], data[3]
        count = 512 if mode & 1 else 256
        glyphs = [data[4 + i * size : 4 + (i + 1) * size] for i in range(count)]
        width, height = 8, size
        if mode & 6:
            unicode_table = data[4 + count * size :]
        table: list[list[int]] = []
        current: list[int] = []
        for i in range(0, len(unicode_table) - 1, 2):
            value = unicode_table[i] | unicode_table[i + 1] << 8
            if value == 0xFFFF:
                table.append(current)
                current = []
            elif value != 0xFFFE:
                current.append(value)
    elif data[:4] == PSF2_MAGIC:
        _, header, flags, length, size, height, width = struct.unpack("<7I", data[4:32])
        glyphs = [data[header + i * size : header + (i + 1) * size] for i in range(length)]
        table = []
        if flags & 1:
            current = []
            raw = data[header + length * size :]
            i = 0
            while i < len(raw) and len(table) < length:
                byte = raw[i]
                if byte == 0xFF:
                    table.append(current)
                    current = []
                    i += 1
                elif byte == 0xFE:
                    while i < len(raw) and raw[i] != 0xFF:  # skip combining sequences
                        i += 1
                else:
                    step = 1 if byte < 0x80 else 2 if byte < 0xE0 else 3 if byte < 0xF0 else 4
                    try:
                        current.append(ord(raw[i : i + step].decode("utf-8")))
                    except UnicodeDecodeError:
                        pass
                    i += step
    else:
        raise ValueError(f"{path}: not a PSF font")

    by_code: dict[int, bytes] = {}
    for index, codes in enumerate(table):
        for code in codes:
            by_code.setdefault(code, glyphs[index])
    return width, height, by_code


def compare(path_a: Path, path_b: Path) -> tuple[int, int, int, int]:
    """Return (shared code points, identical glyphs, only in A, only in B)."""
    _, _, a = load_psf(path_a)
    _, _, b = load_psf(path_b)
    shared = set(a) & set(b)
    same = sum(1 for code in shared if a[code] == b[code])
    return len(shared), same, len(set(a) - set(b)), len(set(b) - set(a))


def font_files(directory: Path, pattern: str) -> dict[str, Path]:
    found = {}
    for path in sorted(directory.iterdir()):
        name = path.name
        for suffix in (".psf.gz", ".psf"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        else:
            continue
        if fnmatch.fnmatch(name, pattern):
            found[name] = path
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dir_a", type=Path)
    parser.add_argument("dir_b", type=Path)
    parser.add_argument("--glob", default="*", help="only fonts whose name matches (default: all)")
    parser.add_argument("--min-identical", type=float, default=0.0, metavar="PERCENT")
    parser.add_argument("--quiet", action="store_true", help="print only the total")
    args = parser.parse_args(argv)

    a_files, b_files = font_files(args.dir_a, args.glob), font_files(args.dir_b, args.glob)
    names = sorted(set(a_files) & set(b_files))
    if not names:
        print("no fonts with the same name in both directories", file=sys.stderr)
        return 1
    total_shared = total_same = only_a = only_b = 0
    for name in names:
        shared, same, a_only, b_only = compare(a_files[name], b_files[name])
        total_shared, total_same, only_a, only_b = (
            total_shared + shared, total_same + same, only_a + a_only, only_b + b_only,
        )
        if not args.quiet:
            pct = 100.0 * same / shared if shared else 100.0
            print(f"{name:34} {shared:5} shared, {shared - same:4} differ ({pct:6.2f}% identical)"
                  f"  only-A {a_only} only-B {b_only}")
    pct = 100.0 * total_same / total_shared if total_shared else 100.0
    missing = sorted(set(a_files) ^ set(b_files))
    print(f"TOTAL {len(names)} fonts, {total_shared} code points compared, "
          f"{pct:.2f}% identical; fonts in only one directory: {len(missing)}")
    return 0 if pct >= args.min_identical else 1


if __name__ == "__main__":
    sys.exit(main())

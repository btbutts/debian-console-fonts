"""Read the few font table values that FreeType's Python binding does not expose."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from psf_font_maker.otf2bdf.errors import RenderError

if TYPE_CHECKING:
    from pathlib import Path

DIRECTORY = struct.Struct(">4sIII")
HEADER_SIZE = 12
NUM_TABLES_AT = 4
HHEA = b"hhea"
ASCENDER_AT = 4
DESCENDER_AT = 6


def read_hhea(path: Path) -> tuple[int, int]:
    """Return the ascender and descender of the font's ``hhea`` table, in font units."""
    data = path.read_bytes()
    (count,) = struct.unpack_from(">H", data, NUM_TABLES_AT)
    for index in range(count):
        tag, _, offset, _ = DIRECTORY.unpack_from(data, HEADER_SIZE + index * DIRECTORY.size)
        if tag == HHEA:
            (ascender,) = struct.unpack_from(">h", data, offset + ASCENDER_AT)
            (descender,) = struct.unpack_from(">h", data, offset + DESCENDER_AT)
            return ascender, descender
    message = f"{path}: the font has no hhea table"
    raise RenderError(message)

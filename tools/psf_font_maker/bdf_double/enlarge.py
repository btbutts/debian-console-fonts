"""Enlarge a BDF font by two in both directions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psf_font_maker.common.errors import ToolError

if TYPE_CHECKING:
    from collections.abc import Sequence

FACTOR = 2
BITS_PER_BYTE = 8
KEPT_PROPERTIES = ("FONT_DESCENT", "FONT_ASCENT", "AVERAGE_WIDTH", "DEFAULT_CHAR")
SCALED_PROPERTIES = ("FONT_DESCENT", "FONT_ASCENT", "AVERAGE_WIDTH")


class BdfError(ToolError):
    """The input is not a BDF this tool understands."""


def widen_row(bits: str) -> str:
    """Return *bits* (a string of 0 and 1) with every bit written twice."""
    return "".join(bit * FACTOR for bit in bits)


def row_to_hex(bits: str) -> str:
    """Return the BDF hex text of a row of bits, padded on the right to whole bytes."""
    padded_length = -(-len(bits) // BITS_PER_BYTE) * BITS_PER_BYTE
    padded = bits.ljust(padded_length, "0")
    return f"{int(padded, 2):0{padded_length // 4}X}"


def enlarge_bitmap(rows: Sequence[str], width: int) -> list[str]:
    """Return the hex rows of a *width*-pixel-wide bitmap enlarged by FACTOR."""
    out: list[str] = []
    for hex_row in rows:
        bits = f"{int(hex_row, 16):0{len(hex_row) * 4}b}"[:width]
        wide = row_to_hex(widen_row(bits))
        out.extend([wide] * FACTOR)
    return out


def scaled(fields: Sequence[str], count: int) -> str:
    """Multiply the first *count* integer fields by FACTOR and join them with spaces."""
    values = [int(field) * FACTOR for field in fields[:count]]
    return " ".join(str(value) for value in values)


def convert_glyph(lines: Sequence[str]) -> list[str]:
    """Return the enlarged lines of one STARTCHAR ... ENDCHAR block."""
    out: list[str] = []
    width = 0
    rows: list[str] = []
    in_bitmap = False
    for line in lines:
        key, _, rest = line.partition(" ")
        fields = rest.split()
        if in_bitmap and key != "ENDCHAR":
            rows.append(line.strip())
        elif key == "BBX":
            width = int(fields[0])
            out.append(f"BBX {scaled(fields, 4)}")
        elif key in {"SWIDTH", "DWIDTH"}:
            out.append(f"{key} {scaled(fields, 1)} {fields[1]}")
        elif key == "BITMAP":
            in_bitmap = True
            out.append("BITMAP")
        elif key == "ENDCHAR":
            out.extend(enlarge_bitmap(rows, width))
            out.append("ENDCHAR")
        else:
            out.append(line)
    return out


def split_font(text: str) -> tuple[list[str], dict[str, str], list[list[str]]]:
    """Split BDF *text* into its header lines, kept properties and glyph blocks."""
    header: list[str] = []
    properties: dict[str, str] = {}
    glyphs: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        key, _, rest = line.partition(" ")
        if key == "STARTCHAR":
            current = [line]
        elif current is not None:
            current.append(line)
            if key == "ENDCHAR":
                glyphs.append(current)
                current = None
        elif key in {"FONT", "SIZE", "FONTBOUNDINGBOX"}:
            header.append(line)
        elif key in KEPT_PROPERTIES:
            properties[key] = rest.strip()
    return header, properties, glyphs


def enlarge_header_line(line: str) -> str:
    """Return a FONT, SIZE or FONTBOUNDINGBOX line for the enlarged font."""
    key, _, rest = line.partition(" ")
    fields = rest.split()
    if key == "SIZE":
        return f"SIZE {int(fields[0]) * FACTOR} {' '.join(fields[1:])}"
    if key == "FONTBOUNDINGBOX":
        return f"FONTBOUNDINGBOX {scaled(fields, 4)}"
    return line


def property_lines(properties: dict[str, str]) -> list[str]:
    """Return the property block of the enlarged font."""
    out = [f"STARTPROPERTIES {len(properties)}"]
    for key in KEPT_PROPERTIES:
        if key in SCALED_PROPERTIES and key in properties:
            out.append(f"{key} {int(properties[key]) * FACTOR}")
        elif key in properties:
            out.append(f"{key} {properties[key]}")
    out.append("ENDPROPERTIES")
    return out


def convert(text: str, source_name: str) -> str:
    """Return the BDF *text* enlarged by FACTOR."""
    header, properties, glyphs = split_font(text)
    if not glyphs or not header:
        message = f"{source_name}: no glyphs or no header found"
        raise BdfError(message)
    out = ["STARTFONT 2.1", f"COMMENT {FACTOR}x enlargement of {source_name} (tools/bdf_double.py)"]
    out.extend(enlarge_header_line(line) for line in header)
    out.extend(property_lines(properties))
    out.append(f"CHARS {len(glyphs)}")
    for glyph in glyphs:
        out.extend(convert_glyph(glyph))
    out.append("ENDFONT")
    return "\n".join(out) + "\n"

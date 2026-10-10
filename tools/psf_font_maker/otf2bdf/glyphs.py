"""The data the renderer produces."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Size:
    """The size to render at: a point size on a display of a given resolution (dpi)."""

    point_size: int = 12
    resolution: int = 100


@dataclass
class GlyphBox:
    """The box around a glyph's set pixels and where it sits relative to the origin."""

    width: int
    height: int
    x_offset: int
    y_offset: int


@dataclass
class RenderedGlyph:
    """One rendered glyph: its bitmap cropped to the pixels that are set, and its metrics."""

    code: int
    scalable_width: int
    advance: int
    box: GlyphBox
    rows: list[str]


@dataclass
class BoundingBox:
    """The box that holds every glyph of the font."""

    min_left: int = 0
    max_right: int = 0
    max_ascent: int = 0
    max_descent: int = 0

    @property
    def width(self) -> int:
        """The width of the box."""
        return self.max_right - self.min_left

    @property
    def height(self) -> int:
        """The height of the box."""
        return self.max_ascent + self.max_descent


@dataclass
class FontInfo:
    """What the font file says about itself, and what rendered it."""

    file_name: str
    family: str
    bold: bool
    italic: bool
    freetype_version: str


@dataclass
class Vertical:
    """The ascent and descent of the font at the size it was rendered at."""

    ascent: int
    descent: int


@dataclass
class RenderedFont:
    """A font rendered at one size."""

    info: FontInfo
    size: Size
    vertical: Vertical
    box: BoundingBox = field(default_factory=BoundingBox)
    monospaced: bool = True
    average_width: int = 0
    glyphs: list[RenderedGlyph] = field(default_factory=list)

"""The errors bdf2psf reports."""

from psf_font_maker.common.errors import ToolError


class FontFormatError(ToolError):
    """A font file is not what the tool expects."""


class ClassifyError(ToolError):
    """The glyphs cannot be used for the requested kind of font."""


class EquivalenceError(ToolError):
    """An equivalents or symbols file is malformed."""


class LayoutError(ToolError):
    """The positions could not be assigned."""


class ConversionError(ToolError):
    """The request cannot be carried out."""

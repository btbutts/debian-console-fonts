"""The errors the FreeType tool reports."""

from psf_font_maker.common.errors import ToolError


class FreetypeError(ToolError):
    """No suitable FreeType could be found or built."""

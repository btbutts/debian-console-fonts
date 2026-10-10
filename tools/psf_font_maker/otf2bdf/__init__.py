"""A port of ``otf2bdf``: render a TrueType or OpenType font to a BDF bitmap font.

Run with ``python3 -m psf_font_maker otf2bdf``. Glyphs are rasterised with FreeType
(through the ``freetype-py`` package) exactly as the C tool did: the same glyph
selection, monochrome rendering, bounding boxes, ascent and descent.
"""

"""Compare two sets of PSF console fonts glyph by glyph.

Run with ``python3 -m psf_font_maker compare-fonts DIR_A DIR_B``. Fonts with the same
name in both directories are compared per Unicode value, so differences in glyph
order or in how many symbols share a glyph do not count.
"""

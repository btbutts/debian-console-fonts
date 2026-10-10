"""Build whole sets of console fonts: choose them, convert them and write the files.

Run with ``python3 -m psf_font_maker fonts``. It does what the Makefile used to do in
Make: it picks the fonts that were asked for (faces and code sets), finds their BDF
sources, converts each with bdf2psf, compresses it and writes ``<Codeset>-<Face>.psf.gz``
into the directory it is told to use. The Makefile only passes the options on.
"""

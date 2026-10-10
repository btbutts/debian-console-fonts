"""Regenerate mk/faces.mk from console-setup's Fonts/Makefile.

Run with ``python3 -m psf_font_maker update-faces`` from the repository root, or
``make update-faces``. mk/faces.mk holds the data the Makefile needs: which BDF files make
up each font face, the legacy VGA tables, the face and code set lists, and the list of
faces console-setup considers "good". It is copied verbatim (only FACES and CODESETS are
renamed ALL_FACES and ALL_CODESETS, because those are our command-line options).
"""

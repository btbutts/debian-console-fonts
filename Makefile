# debian-console-fonts: Linux console (PSF) fonts built the way Debian's
# console-setup builds them, from the fonts' upstream sources.
#
# This Makefile only collects your choices and hands them to the Python tool in
# tools/psf_font_maker, which does all the work (choosing fonts, converting,
# compressing, writing). Fetch the sources first (see README.md)
# or use a release tarball, which already has the fonts. Everything the tool reads is in
# this repository (data/ and sources.json, which says where each source is), except FreeType
# in the one case described below.
#
#   make list                       show the fonts that would be built
#   make freetype                   find (or build) the FreeType that DejaVu is drawn with
#   make fonts                      build them into out/*.psf.gz
#   make install DESTDIR=/target    build them into $(DESTDIR)$(FONTDIR)
#   make fonts FACES="Terminus% VGA%" CODESETS="Uni2 Lat15" OUT=/tmp/fonts
#
# Options (command line or environment); anything you leave out has the tool's default:
#   FACES         face patterns, % standing for any text:  Terminus% VGA% DejaVu% Fixed%
#   CODESETS      code sets:  Uni1 Uni2 Uni3  (also Lat15 Lat2 Greek CyrSlav ...)
#   SKIP          face patterns to leave out, e.g. TerminusBoldVGA16
#   POOL          good (the faces offered by default) or all
#   DEJAVU_SIZES, DEJAVU_PROPORTIONAL   how DejaVu is rendered (proportional: set to 1)
#   JOBS          processes to use
#   QUIET         set to 1 to write only warnings and errors while building
#   VERBOSE       set to 1 to list every conversion warning (a summary otherwise)
#   FREETYPE_LIB_DIR  directory holding a libfreetype 2.13.3 or later to use (Buildroot:
#                 $(HOST_DIR)/lib); otherwise one is looked for, and built if none is found
#   FREETYPE_ARCHIVE_DIR  a directory that may already hold the FreeType source archive
#                 (Buildroot: the package's download directory); used instead of downloading
# Where things are:
#   DATA (the code set tables)  SOURCES (sources.json, which says where each font source,
#   and the place FreeType is built in, is)
#   OUT (for `make fonts`)  DESTDIR  PREFIX  FONTDIR (for `make install`)
#   PYTHON  TOOLS
#
# DejaVu is drawn from its TrueType files with FreeType, which must be 2.13.3 or later.
# Before the fonts are made, the tool is asked to find such a FreeType (given by
# FREETYPE_LIB_DIR, built earlier, in a Buildroot host tree, or on the system) and, if there
# is none, to download its source (the "freetype" entry of sources.json) and build it (needs
# a C compiler and network access). That step is skipped when no selected font is drawn from
# TrueType.

SHELL := /bin/sh

DATA    ?= data
OUT     ?= out
SOURCES ?= sources.json
FREETYPE_LIB_DIR ?=
FREETYPE_ARCHIVE_DIR ?=
TOOLS   ?= tools
PYTHON  ?= python3
DESTDIR ?=
PREFIX  ?= /usr
FONTDIR ?= $(PREFIX)/share/consolefonts

PSF = PYTHONPATH="$(abspath $(TOOLS))" $(PYTHON) -m psf_font_maker

# An option is passed on only if it was set (even to nothing, which the tool reports),
# so that the tool's own defaults apply otherwise.
passed = $(if $(filter undefined,$(origin $(1))),,$(2) '$($(1))')

OPTIONS = --data '$(DATA)' --sources '$(SOURCES)' \
	$(call passed,FACES,--faces) \
	$(call passed,CODESETS,--codesets) \
	$(call passed,SKIP,--skip) \
	$(call passed,POOL,--pool) \
	$(call passed,DEJAVU_SIZES,--dejavu-sizes) \
	$(call passed,JOBS,--jobs) \
	$(if $(DEJAVU_PROPORTIONAL),--dejavu-proportional)

# How much the fonts command says (the freetype command has no such options)
TALK = $(if $(QUIET),--quiet) $(if $(VERBOSE),--verbose)

FREETYPE_OPTIONS = $(OPTIONS) \
	$(if $(FREETYPE_LIB_DIR),--lib-dir '$(FREETYPE_LIB_DIR)') \
	$(if $(FREETYPE_ARCHIVE_DIR),--archive-dir '$(FREETYPE_ARCHIVE_DIR)')

# Make the fonts into $(1): first the FreeType step, which prints the directory of the
# library to use (nothing if none is needed or the system finds it itself), then the fonts.
define make_fonts
dir=$$($(PSF) freetype $(FREETYPE_OPTIONS)) || exit $$?; \
$(PSF) fonts $(OPTIONS) $(TALK) $${dir:+--freetype-lib-dir "$$dir"} --out '$(1)'
endef

.DEFAULT_GOAL := fonts
.PHONY: fonts list freetype install clean distclean help

fonts:
	@$(call make_fonts,$(OUT))

list:
	@dir=$$($(PSF) freetype $(FREETYPE_OPTIONS)) || exit $$?; \
	$(PSF) fonts $(OPTIONS) $${dir:+--freetype-lib-dir "$$dir"} --list

freetype:
	@$(PSF) freetype $(FREETYPE_OPTIONS) --always

install:
	@$(call make_fonts,$(DESTDIR)$(FONTDIR))

clean:
	rm -rf '$(OUT)'

distclean: clean
	@$(PSF) freetype $(FREETYPE_OPTIONS) --clean

help:
	@sed -n '/^#   make list/,/^#   PYTHON  TOOLS/p' Makefile | sed 's/^# \{0,1\}//'

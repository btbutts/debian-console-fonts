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
#   QUIET, VERBOSE  how much is said while the fonts are made (set to 1). The configuration,
#                 every check of the build environment, the stages and the warnings are
#                 always written. QUIET: a line per family and code set, and a heartbeat;
#                 default: also each face and the percentage; VERBOSE: also each font and
#                 every conversion warning
# Optional, and normally not needed (the tool finds a FreeType, in a Buildroot host tree too):
#   FREETYPE_LIB_DIR  directory holding a libfreetype 2.13.3 or later to use instead of
#                 looking for one
#   FREETYPE_ARCHIVE_DIR  a directory that may already hold the FreeType source archive;
#                 used instead of downloading it
# Where things are:
#   DATA (the code set tables)  SOURCES (sources.json, which says where each font source,
#   and the place FreeType is built in, is)
#   OUT (for `make fonts`)  DESTDIR  PREFIX  FONTDIR (for `make install`)
#   PYTHON  TOOLS
#
# DejaVu is drawn from its TrueType files with the freetype-py package and a FreeType that
# must be 2.13.3 or later. Before any font is made, the tool writes down what you asked for
# and checks what that needs: where freetype-py is, and which FreeType is used (given by
# FREETYPE_LIB_DIR, built earlier, in a Buildroot host tree, or on the system). If there is
# none it downloads FreeType's source (the "freetype" entry of sources.json) and builds it
# (needs a C compiler and network access). Nothing of this is looked at when no selected
# font is drawn from TrueType.

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

# What the fonts command is told about FreeType. It checks everything the selection needs
# (and finds or builds a FreeType) before it builds any font, and logs what it did.
FONTS_FREETYPE = \
	$(if $(FREETYPE_LIB_DIR),--freetype-lib-dir '$(FREETYPE_LIB_DIR)') \
	$(if $(FREETYPE_ARCHIVE_DIR),--freetype-archive-dir '$(FREETYPE_ARCHIVE_DIR)')

define make_fonts
$(PSF) fonts $(OPTIONS) $(TALK) $(FONTS_FREETYPE) --out '$(1)'
endef

.DEFAULT_GOAL := fonts
.PHONY: fonts list freetype install clean distclean help

fonts:
	@$(call make_fonts,$(OUT))

list:
	@$(PSF) fonts $(OPTIONS) $(TALK) $(FONTS_FREETYPE) --list

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

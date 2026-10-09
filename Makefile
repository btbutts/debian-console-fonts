# debian-console-fonts: Linux console (PSF) fonts built the way Debian's
# console-setup builds them.
#
# Derived from console-setup's Fonts/Makefile (GPL-2.0-or-later, Copyright (C)
# Anton Zinoviev and others). It runs console-setup's own bdf2psf and
# fontcodesets scripts with the same arguments, names and gzip settings, but
# works from a merged tree in which upstream BDFs take precedence over the ones
# bundled with console-setup. No network access: run the downloader first (see
# README.md) or use a release tarball, which already contains sources/.
#
#   make list                 show the fonts that would be built
#   make fonts                build them into out/*.psf.gz
#   make fonts FACES="Terminus% VGA%" CODESETS="Uni2 Lat15" OUT=/tmp/fonts
#
# Options (command line or environment):
#   FACES         patterns for <Face><size>, e.g. Terminus% DejaVuBold%  (one % each)
#   CODESETS      code sets, e.g. Uni1 Uni2 Uni3 Lat15 Greek CyrSlav
#   SKIP          <Face><size> patterns to leave out, e.g. TerminusBoldVGA16
#   POOL          good (console-setup's default faces) or all
#   USE_UPSTREAM  sources whose BDFs replace console-setup's (default below)
#   SRC BUILD OUT PERL GZIP PYTHON

SHELL := /bin/sh

SRC          ?= sources
BUILD        ?= build
OUT          ?= out
PERL         ?= perl
GZIP         ?= gzip -9n
PYTHON       ?= python3

FACES        ?= Terminus% VGA% DejaVu% Fixed%
CODESETS     ?= Uni1 Uni2 Uni3
SKIP         ?=
POOL         ?= good
USE_UPSTREAM ?= terminus-font uni-vga

# BDF files each upstream source may replace in console-setup's bdf/ directory.
OVERLAY_terminus-font := ter-u*.bdf
OVERLAY_uni-vga       := u_vga16.bdf
OVERLAY_ucs-fonts     := 7x14.bdf 7x14B.bdf 8x13.bdf 8x13B.bdf 8x13O.bdf 9x15.bdf 9x15B.bdf 9x18.bdf 9x18B.bdf

.DEFAULT_GOAL := fonts
.DELETE_ON_ERROR:
.SECONDARY:

include mk/faces.mk

# When a VGA face has no BDF list for a code set, console-setup falls back to these.
VGA8-DEFAULT     := legacy8a.bdf
VGA10-DEFAULT    := legacy10a.bdf
VGA12-DEFAULT    := legacy12a.bdf
VGA14-DEFAULT    := legacy14a.bdf
VGA16-DEFAULT    := u_vga16.bdf
VGA19-DEFAULT    := legacy19a.bdf
VGA28x16-DEFAULT := legacy14a-double.bdf
VGA32x16-DEFAULT := u_vga16-double.bdf

# Faces wider than 8 pixels are framebuffer-only fonts (bdf2psf --fb).
FB_SUFFIXES := x6 x10 x11 x12 x14 x16 x20 x24 x28 x32 x40 x48 x64

CS        := $(SRC)/console-setup/Fonts
STAGE     := $(abspath $(BUILD))/Fonts
STAGED    := $(BUILD)/.staged
LOCK      := $(wildcard $(SRC)/sources.lock.json)

# --- selection ---------------------------------------------------------------

POOL_FACES     := $(if $(filter all,$(POOL)),$(ALL_FACES),$(GOOD_FACES))
SELECTED       := $(filter $(FACES),$(POOL_FACES))
SELECTED_PLAIN := $(filter-out $(LEGACY_FACES),$(SELECTED))

# build/coverage/<Face>.mk (made below, from fontcodesets) defines COVER.<Face>.
# It must be included before CHOSEN is computed; make remakes it and restarts.
# Needed to know what to build, but not by clean, help or update-faces.
ifneq ($(filter-out clean help update-faces,$(or $(MAKECMDGOALS),fonts)),)
include $(addprefix $(BUILD)/coverage/,$(addsuffix .mk,$(SELECTED_PLAIN)))
endif

# Code sets a face covers: computed from its BDFs (fontcodesets) except for the
# VGA faces, which console-setup lists by hand.
face_codesets = $(if $(filter $(1),$(LEGACY_FACES)),$($(1)-CODESETS),$(COVER.$(1)))

CHOSEN := $(sort $(foreach f,$(SELECTED),$(addsuffix -$(f),$(filter $(CODESETS),$(call face_codesets,$(f))))))
CHOSEN := $(filter-out $(addprefix %-,$(SKIP)),$(CHOSEN))

# --- per-font arguments (name = <Codeset>-<Face><size>) -----------------------

cs_of       = $(word 1,$(subst -, ,$(1)))
face_of     = $(word 2,$(subst -, ,$(1)))
base_cs     = $(patsubst Full%,%,$(call cs_of,$(1)))
fontset     = $(firstword $(wildcard $(CS)/fontsets/$(call base_cs,$(1)).*))

bdf_list    = $(strip $(if $(filter $(call face_of,$(1)),$(LEGACY_FACES)), \
                $(or $(strip $($(call base_cs,$(1))-legacy$(patsubst VGA%,%,$(call face_of,$(1)))-BDFS)),$($(call face_of,$(1))-DEFAULT)), \
                $($(call face_of,$(1))-BDFS)))
bdf_arg     = $(STAGE)/bdf/$(subst +,+$(STAGE)/bdf/,$(call bdf_list,$(1)))
equiv_arg   = $(if $(filter Full%,$(call cs_of,$(1))),/dev/null,$(STAGE)/standard.equivalents$(if $(findstring Uni1,$(call cs_of,$(1))),+$(STAGE)/arabic.equivalents))
symbol_arg  = $(STAGE)/ascii.set+$(STAGE)/linux.set+$(STAGE)/fontsets/$(notdir $(call fontset,$(1)))+:$(STAGE)/useful.set
size_arg    = $(if $(filter Full%,$(call cs_of,$(1))),512,$(patsubst .%,%,$(suffix $(call fontset,$(1)))))
fb_flag     = $(if $(filter $(addprefix %,$(FB_SUFFIXES)),$(call face_of,$(1))),--fb)

# --- goals ---------------------------------------------------------------------

.PHONY: fonts list clean help update-faces FORCE
FORCE:

fonts: $(addprefix $(OUT)/,$(addsuffix .psf.gz,$(CHOSEN)))
	@echo "$(words $(CHOSEN)) fonts in $(OUT)/"

list:
	@printf '%s\n' $(CHOSEN)
	@echo "$(words $(CHOSEN)) fonts" >&2

help:
	@sed -n '/^#   make list/,/^#   SRC BUILD/p' Makefile | sed 's/^# \{0,1\}//'

update-faces:
	$(PYTHON) tools/update-faces.py

clean:
	rm -rf $(BUILD) $(OUT)

# --- staged tree ---------------------------------------------------------------
# build/Fonts mirrors console-setup's Fonts/ directory (symlinks), with the BDFs
# of the USE_UPSTREAM sources replacing the bundled ones. bdf2psf and
# fontcodesets then run unchanged.

$(BUILD)/.use-upstream: FORCE
	@mkdir -p $(BUILD)
	@echo '$(USE_UPSTREAM)' | cmp -s - $@ 2>/dev/null || echo '$(USE_UPSTREAM)' > $@

define overlay
	@if [ -d "$(abspath $(SRC))/$(1)" ]; then \
	  for f in $(foreach p,$(OVERLAY_$(1)),"$(abspath $(SRC))/$(1)"/$(p)); do \
	    [ -e "$$f" ] && ln -sf "$$f" "$(STAGE)/bdf/$$(basename "$$f")"; \
	  done; true; \
	else echo "note: $(SRC)/$(1) not found, using console-setup's BDFs for it" >&2; fi
endef

$(STAGED): $(LOCK) $(BUILD)/.use-upstream Makefile mk/faces.mk
	@test -f "$(CS)/bdf2psf" || { echo "error: $(CS)/bdf2psf not found; fetch the sources first (see README.md)" >&2; exit 1; }
	rm -rf "$(STAGE)"
	mkdir -p "$(STAGE)/bdf"
	@for f in "$(abspath $(CS))"/*; do n=$${f##*/}; [ "$$n" = bdf ] || ln -s "$$f" "$(STAGE)/$$n"; done
	@for f in "$(abspath $(CS))"/bdf/*.bdf; do ln -s "$$f" "$(STAGE)/bdf/$${f##*/}"; done
	$(foreach s,$(USE_UPSTREAM),$(call overlay,$(s))$(newline))
	@touch $@

define newline


endef

# --- code set coverage per face ------------------------------------------------

$(BUILD)/coverage/%.mk: $(STAGED)
	@mkdir -p $(dir $@)
	@printf 'COVER.$*:=%s\n' "$$(cd "$(STAGE)" && $(PERL) ./fontcodesets '$($*-BDFS)' 2>/dev/null)" > $@.tmp
	@mv $@.tmp $@

# --- one rule pair per font -----------------------------------------------------

define font_rule
$(BUILD)/fonts/$(1).psf: $(STAGED)
	@mkdir -p $(BUILD)/fonts
	$(PERL) "$(STAGE)/bdf2psf" $(call fb_flag,$(1)) --log "$(BUILD)/fonts/$(1).log" \
	    "$(call bdf_arg,$(1))" "$(call equiv_arg,$(1))" "$(call symbol_arg,$(1))" $(call size_arg,$(1)) "$$@" \
	    2>"$(BUILD)/fonts/$(1).err" || { cat "$(BUILD)/fonts/$(1).err" >&2; exit 1; }

$(OUT)/$(1).psf.gz: $(BUILD)/fonts/$(1).psf
	@mkdir -p $(OUT)
	$(GZIP) < $$< > $$@
endef

$(foreach n,$(CHOSEN),$(eval $(call font_rule,$(n))))

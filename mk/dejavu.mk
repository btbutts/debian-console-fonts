# DejaVu console fonts rendered from the original TTFs, the way Debian's pre-rendered
# BDFs were made: the otf2bdf renderer at a cell width of N, then bdf2psf. Included by the
# Makefile. Rendering needs the freetype-py package.
# Active when `dejavu` is in USE_UPSTREAM; otherwise Debian's own dejavu-u*.bdf are used.
#
#   DEJAVU_SIZES         cell widths to render (default: Debian's eight sizes)
#   DEJAVU_PROPORTIONAL  non-empty adds the 18 proportional faces (off by default;
#                        glyphs wider than the cell are dropped)

DEJAVU_SIZES        ?= 16 20 24 28 32 40 48 64
DEJAVU_PROPORTIONAL ?=

# <face>:<ttf file name without .ttf>
DEJAVU_MONO := DejaVu:DejaVuSansMono DejaVuBold:DejaVuSansMono-Bold \
	DejaVuOblique:DejaVuSansMono-Oblique DejaVuBoldOblique:DejaVuSansMono-BoldOblique
DEJAVU_PROP := DejaVuSans:DejaVuSans DejaVuSansBold:DejaVuSans-Bold \
	DejaVuSansOblique:DejaVuSans-Oblique DejaVuSansBoldOblique:DejaVuSans-BoldOblique \
	DejaVuSansExtraLight:DejaVuSans-ExtraLight \
	DejaVuSansCondensed:DejaVuSansCondensed DejaVuSansCondensedBold:DejaVuSansCondensed-Bold \
	DejaVuSansCondensedOblique:DejaVuSansCondensed-Oblique \
	DejaVuSansCondensedBoldOblique:DejaVuSansCondensed-BoldOblique \
	DejaVuSerif:DejaVuSerif DejaVuSerifBold:DejaVuSerif-Bold \
	DejaVuSerifItalic:DejaVuSerif-Italic DejaVuSerifBoldItalic:DejaVuSerif-BoldItalic \
	DejaVuSerifCondensed:DejaVuSerifCondensed DejaVuSerifCondensedBold:DejaVuSerifCondensed-Bold \
	DejaVuSerifCondensedItalic:DejaVuSerifCondensed-Italic \
	DejaVuSerifCondensedBoldItalic:DejaVuSerifCondensed-BoldItalic \
	DejaVuMath:DejaVuMathTeXGyre

DEJAVU_ACTIVE := $(filter dejavu,$(USE_UPSTREAM))
DEJAVU_TABLE  := $(DEJAVU_MONO) $(if $(DEJAVU_PROPORTIONAL),$(DEJAVU_PROP))
DEJAVU_NAMES  := $(foreach e,$(DEJAVU_TABLE),$(firstword $(subst :, ,$(e))))
DEJAVU_TTFS   := $(SRC)/dejavu/ttf

# Does FACES ask for any DejaVu face? Only then is FreeType (freetype-py) needed.
DEJAVU_NEEDED := $(and $(DEJAVU_ACTIVE),$(or $(filter DejaVu%,$(FACES)),$(filter $(FACES),$(DEJAVU_NAMES))))

# Cell height (FONT_ASCENT + FONT_DESCENT) per size; it is part of Debian's face names
# (DejaVu30x16) and only otf2bdf can tell. Made by the rule below, included below.
ifneq ($(DEJAVU_NEEDED),)
ifneq ($(filter-out clean help update-faces,$(or $(MAKECMDGOALS),fonts)),)
include $(BUILD)/dejavu/heights.mk
endif
endif

$(BUILD)/dejavu/.sizes: FORCE
	@mkdir -p $(dir $@)
	@echo '$(DEJAVU_SIZES)' | cmp -s - $@ 2>/dev/null || echo '$(DEJAVU_SIZES)' > $@

$(BUILD)/dejavu/heights.mk: $(PSF_SOURCES) $(BUILD)/dejavu/.sizes $(DEJAVU_TTFS)/DejaVuSansMono.ttf
	@{ for p in $(DEJAVU_SIZES); do \
	  h=$$($(PSF) otf2bdf --height -p $$p -r 115 "$(DEJAVU_TTFS)/DejaVuSansMono.ttf") || exit 1; \
	  printf 'DJH.%s:=%s\n' $$p $$h; \
	done; echo 'DJH_READY:=1'; } > $@.tmp
	@mv $@.tmp $@

# dejavu_face(face, size, ttf): names, BDF list and rendering rule for one face.
define dejavu_face
$(1)$(DJH.$(2))x$(2)-BDFS := dejavu-$(1)-$(2).bdf
$(BUILD)/Fonts/bdf/dejavu-$(1)-$(2).bdf: $(STAGED) $(PSF_SOURCES) $(DEJAVU_TTFS)/$(3).ttf
	$(PSF) otf2bdf -c C -p $(2) -r 115 --cell-width $(2) -o "$$@.tmp" "$(DEJAVU_TTFS)/$(3).ttf"
	@mv "$$@.tmp" "$$@"
$(BUILD)/coverage/$(1)$(DJH.$(2))x$(2).mk: $(BUILD)/Fonts/bdf/dejavu-$(1)-$(2).bdf
endef

DEJAVU_FACES :=
ifneq ($(DJH_READY),)
DEJAVU_FACES := $(foreach s,$(DEJAVU_SIZES),$(foreach n,$(DEJAVU_NAMES),$(n)$(DJH.$(s))x$(s)))
$(foreach s,$(DEJAVU_SIZES),$(foreach e,$(DEJAVU_TABLE),\
  $(eval $(call dejavu_face,$(firstword $(subst :, ,$(e))),$(s),$(lastword $(subst :, ,$(e)))))))
endif

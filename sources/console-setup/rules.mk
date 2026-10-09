ifndef RULES_MK
RULES_MK:=a conditional to make it included only once
###########################################################################

SHELL = /bin/sh

build : build-linux build-mini-linux

.PHONY: build build-linux build-common
build-common:
build-linux: build-common
.PHONY: build-mini-linux
build-mini-linux: build-linux
.PHONY: clean maintainer-clean

%.gz : %
	gzip -9n <$< >$@

###########################################################################
endif

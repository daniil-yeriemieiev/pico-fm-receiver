# Minimal Makefile for Sphinx documentation

SPHINXBUILD ?= python -m sphinx
SOURCEDIR   = .
BUILDDIR    = _build

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(O)

.PHONY: help Makefile

# Any target (for example "html") is passed to sphinx-build
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(O)

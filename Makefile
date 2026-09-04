PYTHON ?= ./.venv/bin/python
MYJS_PKG := packaging/myjs
VERSION := $(shell cat VERSION)   # single source of truth for both distributions

.PHONY: test install lint clean build deploy version bump \
        myjs-clean myjs-build myjs-check myjs-install myjs-publish

version:
	@echo $(VERSION)

# make bump V=0.0.3  -- bumps VERSION and the myjs->domonic-libs lockstep floor
bump:
	@test -n "$(V)" || (echo "usage: make bump V=X.Y.Z" && exit 1)
	@printf '%s\n' "$(V)" > VERSION
	@sed -i.bak 's/"domonic-libs>=[0-9.]*"/"domonic-libs>=$(V)"/' $(MYJS_PKG)/pyproject.toml && rm $(MYJS_PKG)/pyproject.toml.bak
	@echo "VERSION -> $(V)   then: git tag v$(V) && git tag myjs-v$(V) && git push --tags"

test:
	$(PYTHON) -m pytest

install:
	$(PYTHON) -m pip install -r requirements.txt

lint:
	$(PYTHON) -m py_compile $(shell git ls-files --cached --others --exclude-standard '*.py')

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf build/ dist/ src/domonic_libs.egg-info/

build: clean
	$(PYTHON) -m build
	rm -rf build/

# Publishes domonic-libs $(VERSION) to PyPI. Needs domonic (the pinned version)
# on PyPI, a green CI run, and a matching tag: git tag v$(VERSION) && git push --tags
deploy: build
	$(PYTHON) -m twine check dist/*
	$(PYTHON) -m twine upload dist/*

# --- myjs: its own distribution on PyPI --------------------------------------
# packaging/myjs/ builds the standalone `myjs` package. src/myjs is the single
# source of truth -- packaging/myjs/src is a symlink to ../../src, and the
# pyproject there packages only `myjs*`.

myjs-clean:
	rm -rf $(MYJS_PKG)/dist $(MYJS_PKG)/build src/myjs.egg-info

myjs-build: myjs-clean
	$(PYTHON) -m build $(MYJS_PKG)
	rm -rf $(MYJS_PKG)/build src/myjs.egg-info

myjs-check: myjs-build
	$(PYTHON) -m twine check $(MYJS_PKG)/dist/*

myjs-install:
	$(PYTHON) -m pip install -e $(MYJS_PKG) --no-deps

# Publish `myjs` $(VERSION) to PyPI. Needs domonic-libs $(VERSION) already on
# PyPI, a green CI run, and a tag: git tag myjs-v$(VERSION) && git push --tags
myjs-publish: myjs-check
	$(PYTHON) -m twine upload $(MYJS_PKG)/dist/*

PYTHON ?= ./.venv/bin/python

.PHONY: test install lint clean build deploy

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

# Publishes to PyPI. Requires domonic >= 1.5.0 to already be on PyPI, a green
# CI run, and a matching git tag (git tag v$(VERSION) && git push --tags).
deploy: build
	$(PYTHON) -m twine upload dist/*

# Publishing

This repo produces **two** PyPI distributions from one source tree, kept in
**lockstep on a single version** — the repo-root [`VERSION`](../VERSION) file:

| Distribution | Source | Provides | Depends on |
| --- | --- | --- | --- |
| [`domonic-libs`](https://pypi.org/project/domonic-libs/) | `src/domonic_libs/` | the ports (DOMPurify, marked, preact, mermaid, dagre, …), the `acorn` parser + interpreter, the conformance / js262 runners, `dlx` CLI | `domonic>=1.7.0` |
| [`myjs`](https://pypi.org/project/myjs/) | `src/myjs/` (built via `packaging/myjs/`) | the `myjs` JavaScript runtime + REPL + `ffi` + host bindings | `domonic-libs>=<same version>` |

`VERSION` is the only place the number lives:

- both `pyproject.toml` files use `dynamic = ["version"]` with `version = {file = "VERSION"}` (`packaging/myjs/VERSION` is a symlink to `../../VERSION`);
- `domonic_libs.__version__` / `myjs.__version__` read `VERSION` in a source checkout, else fall back to installed metadata;
- `make bump V=X.Y.Z` writes `VERSION` and updates the `myjs → domonic-libs` floor.

`myjs` is a thin layer on top of `domonic_libs.acorn`, so it releases *after*
`domonic-libs`. The chain — and the release order — is:

```
domonic X  →  domonic-libs <VERSION>  →  myjs <VERSION>
```

Each package is only installable from PyPI once the one to its left is up.
The main `pyproject.toml` pins `domonic>=1.7.0` (this release's fixes --
`String`/`Number` as real `str`/`float` subclasses, `getComputedStyle`
dot-access, JSON-number normalisation, uppercase `tagName`, ... -- depend on
1.7.0 behaviour a 1.6.0 install doesn't have). **`domonic 1.7.0` is published**,
so `domonic-libs 0.0.3` / `myjs 0.0.3` are clear to go out.

## Cutting a release

```bash
make bump V=0.0.3          # -> VERSION, and the myjs dependency floor
make test                 # green
git commit -am "release 0.0.3"
git tag v0.0.3            # domonic-libs
git tag myjs-v0.0.3      # myjs
git push --tags
```

### domonic-libs

```bash
make build      # clean + python -m build  ->  dist/
make deploy     # build + twine check + twine upload dist/*
```

Tagging `v*` does not trigger CI publishing today — `make deploy` is manual.

### myjs

`packaging/myjs/` holds the `myjs` distribution's `pyproject.toml`. `src` and
`VERSION` there are **symlinks** to the repo root, so `src/myjs/` and `VERSION`
stay the single sources of truth and the project packages only `myjs*`.

```bash
make myjs-build     # -> packaging/myjs/dist/
make myjs-check     # twine check
make myjs-install   # pip install -e packaging/myjs  (local dev)
make myjs-publish   # check + twine upload
```

CI: pushing a tag matching `myjs-v*` runs `.github/workflows/myjs-publish.yml`,
which builds, verifies the wheel, and publishes via **PyPI Trusted Publishing**
(OIDC — no token secret; configure a pending publisher for the `myjs` project
pointing at `byteface/domonic-libs`, workflow `myjs-publish.yml`, environment
`pypi`). `workflow_dispatch` builds and checks without publishing.

## The test suite

`requirements.txt` installs both packages editable (`-e .[dev]` then
`-e ./packaging/myjs`), so `tests/test_myjs.py` and `tests/test_js262.py` see
`import myjs`. The main `Tests` workflow does the same.

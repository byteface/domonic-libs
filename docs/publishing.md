# Publishing

This repo produces **three** PyPI distributions from one source tree, kept in
**lockstep on a single version** — the repo-root [`VERSION`](../VERSION) file:

| Distribution | Source | Provides | Depends on |
| --- | --- | --- | --- |
| [`domonic-libs`](https://pypi.org/project/domonic-libs/) | `src/domonic_libs/` | the ports (DOMPurify, marked, preact, mermaid, dagre, …), the `acorn` parser + interpreter, the conformance / js262 runners, `dlx` CLI | `domonic>=1.7.0` |
| [`myjs`](https://pypi.org/project/myjs/) | `src/myjs/` (built via `packaging/myjs/`) | the `myjs` JavaScript runtime + REPL + `ffi` + host bindings | `domonic-libs>=<same version>` |
| `htmlparser2` | `src/htmlparser2/` (built via `packaging/htmlparser2/`) | the standalone `htmlparser2` import, CLI, and domonic parser adapter | `domonic>=1.7.0` |

`VERSION` is the only place the number lives:

- all package `pyproject.toml` files use `dynamic = ["version"]` with `version = {file = "VERSION"}` (`packaging/myjs/VERSION` and `packaging/htmlparser2/VERSION` are symlinks to `../../VERSION`);
- `domonic_libs.__version__` / `myjs.__version__` / `htmlparser2.__version__` read `VERSION` in a source checkout, else fall back to installed metadata;
- `make bump V=X.Y.Z` writes `VERSION` and updates the `myjs → domonic-libs` floor.

`myjs` is a thin layer on top of `domonic_libs.acorn`, so it releases *after*
`domonic-libs`. The chain — and the release order — is:

```
domonic X  →  domonic-libs <VERSION>  →  myjs <VERSION>
          ↘  htmlparser2 <VERSION>
```

Each package is only installable from PyPI once the one to its left is up.
The main `pyproject.toml` pins `domonic>=1.7.0` (this release's fixes --
`String`/`Number` as real `str`/`float` subclasses, `getComputedStyle`
dot-access, JSON-number normalisation, uppercase `tagName`, ... -- depend on
1.7.0 behaviour a 1.6.0 install doesn't have). **`domonic 1.7.0` is published**,
so `domonic-libs 0.0.4` / `myjs 0.0.4` / `htmlparser2 0.0.4` are clear to go out.

## Cutting a release

```bash
make bump V=0.0.4          # -> VERSION, and the myjs dependency floor
make test                 # green
git commit -am "release 0.0.4"
git tag v0.0.4            # domonic-libs
git tag myjs-v0.0.4       # myjs
git tag htmlparser2-v0.0.4
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

### htmlparser2

`packaging/htmlparser2/` holds the standalone parser distribution. `src` and
`VERSION` there are symlinks to the repo root, so `src/htmlparser2/` and
`VERSION` stay the single sources of truth and the project packages only
`htmlparser2*`.

```bash
make htmlparser2-build
make htmlparser2-check
make htmlparser2-install
make htmlparser2-publish
```

CI: pushing a tag matching `htmlparser2-v*` runs
`.github/workflows/htmlparser2-publish.yml`, which builds, verifies the wheel,
and publishes via PyPI Trusted Publishing.

## The test suite

`requirements.txt` installs the standalone packages editable (`-e .[dev]`,
`-e ./packaging/myjs`, and `-e ./packaging/htmlparser2`), so tests see
`import myjs` and `import htmlparser2`. The main `Tests` workflow does the same.

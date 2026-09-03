# domonic-libs

[![Tests](https://github.com/byteface/domonic-libs/actions/workflows/tests.yml/badge.svg)](https://github.com/byteface/domonic-libs/actions/workflows/tests.yml)
<!-- [![PyPI version](https://img.shields.io/pypi/v/domonic-libs.svg)](https://pypi.org/project/domonic-libs/) -->
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

DOM-shaped Python ports and an optional pywebview app wrapper built on [domonic](https://github.com/byteface/domonic).


## Experimental libraries

Additional ports and experimental libraries not included with the standard domonic installation.

This package is deliberately split:

- libs for compatibility testing domonic.
- an `app` wrapper for building desktop UIs from domonic trees.

but they will be here so you can use them in an app if you want by importing off the tags here.

DOM behaviours that trip up the ports are logged in [docs/domonic-wrinkles.md](docs/domonic-wrinkles.md) to feed back upstream.

## Install

To get all the libraries like Mermaid, preact, turndown, marked, validator, qs, dompurify, readability etc...

```bash
pip install domonic-libs
```

The pywebview app wrapper is an optional extra:

```bash
pip install "domonic-libs[app]"
```

Hack on the repo and run examples:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt   # editable install + dev deps
./.venv/bin/python examples/dompurify_demo.py
make test
```

The app wrapper API is in [docs/app.md](docs/app.md); the `dlx` CLI in [docs/cli.md](docs/cli.md). Ported modules keep their upstream licenses -- see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Command line -- `dlx`

Installing the package puts a `dlx` command on your `PATH` (also aliased `domonic-libs`, or run it as `python -m domonic_libs`). The cleanest way to get just the CLI, isolated, is [pipx](https://pipx.pypa.io):

```bash
pipx install domonic-libs

# ...or run it once without installing
pipx run --spec domonic-libs dlx --help
```

Every text command reads a file argument, or **stdin** when the argument is `-` or omitted, and writes to `--output` / `-o` or **stdout** -- so they pipe.

```bash
# Mermaid -> SVG (flowchart / sequence / pie / timeline, auto-detected)
dlx mermaid architecture.mmd -o architecture.svg
dlx mermaid architecture.mmd --open           # render + open in the browser
dlx mermaid architecture.mmd --stats          # counts on stderr
cat flow.mmd | dlx mermaid --html > flow.html

# Markdown <-> HTML
echo "# Hi *there*" | dlx md
dlx html2md article.html --gfm > article.md

# Pull the readable article out of a page
dlx read https://example.com/some/post --md > post.md
dlx read page.html --json                      # just the metadata

# Sanitise hostile HTML (DOMPurify)
dlx sanitize comment.html --profile html --report

# One-off validator.js checks (exit 0 = true, 1 = false)
dlx validate isEmail ada@example.com
dlx validate isIBAN DE89370400440532013000
dlx validate --list

# Query strings
dlx qs parse "user[name]=ada&tags[]=a&tags[]=b"
dlx qs stringify '{"a": 1, "b": {"c": 2}}'

# Lay out and draw an arbitrary graph with the dagre port
printf 'build -> test\ntest -> deploy\nbuild -> lint\nlint -> deploy\n' \
  | dlx dagre --rankdir LR -o pipeline.svg
```

`dlx <command> -h` lists each command's options; full reference in [docs/cli.md](docs/cli.md).

## Library Ports

The domonic repo has tests but also small complex ports like javascript and libraries like dquery and d3 were done to make sure the DOM was behaving as it should.

The more things I can port faithfully from js, the more expectations on the DOM I can correct. And out of that will also pop useful tools.

### DOMPurify

```python
from domonic_libs.dompurify import sanitize

clean = sanitize('<p onclick="x"><a href="javascript:bad()">bad</a>Hello</p>')
print(clean)
```

A port of [DOMPurify](https://github.com/cure53/DOMPurify) -- config options, hooks, namespaces, `RETURN_DOM` / `WHOLE_DOCUMENT`, and DOM-clobbering protection. It runs DOMPurify's own `test/fixtures/expect.mjs` corpus (`tests/fixtures/dompurify/expect.json`, 223 real-world XSS payloads) at **212/223 exact-match** with default config; the remaining eleven are fidelity gaps (safe output, not byte-identical) from domonic's HTML5 parser or DOMPurify's deepest namespace-confusion checks, listed in `tests/test_dompurify.py::KNOWN_GAPS`.

### QS

```python
from domonic_libs.qs import parse, stringify

state = parse("filters[status][]=open&filters[status][]=draft")
print(state)
print(stringify(state, {"arrayFormat": "brackets"}))
```

`qs` is useful when browser-style URL state needs to round-trip through nested Python dictionaries and arrays.

### validator

```python
from domonic_libs import validator

validator.isEmail("ada@example.com")            # True
validator.isIBAN("DE89370400440532013000")      # True (mod-97 checksum)
validator.isCreditCard("4111111111111111")      # True (Luhn)
validator.normalizeEmail("Foo.Bar+x@googlemail.com")  # 'foobar@gmail.com'
```

A file-by-file port of [validator.js](https://github.com/validatorjs/validator.js) v13 -- ~90 string validators and sanitizers with the upstream camelCase names. Options are passed as a dict or as keyword arguments. It runs the `valid` / `invalid` case tables from validator.js's own test suite (`tests/fixtures/validator/cases.json`, 858 cases). Locale-table-heavy validators (`isMobilePhone`, `isPostalCode`, `isTaxID`, ...) and the full `normalizeEmail` provider lists are not ported yet.

### Readability And Turndown

```python
from domonic_libs.readability import Readability
from domonic_libs.turndown import turndown, TurndownService

article = Readability(html).parse()
markdown = turndown(article["content"])

# TurndownService mirrors turndown.js: options, .use(plugin), .addRule,
# .keep, .remove. Python option names are snake_case (heading_style="atx").
service = TurndownService(heading_style="atx", code_block_style="fenced")

from domonic_libs.turndown.gfm import gfm
service.use(gfm)  # tables, strikethrough, task lists (turndown-plugin-gfm port)
```

`turndown` is a file-for-file port of [turndown.js](https://github.com/mixmark-io/turndown) and runs its upstream fixture suite (see `tests/test_turndown.py`). Together with Readability it is useful for content extraction, reader views, local archives, and LLM-friendly page summaries.

### marked

```python
from domonic_libs.marked import marked

marked("# Title\n\nSome **bold** text and a [link](https://x.io).")
```

A file-for-file port of [marked](https://github.com/markedjs/marked) v18 (Markdown to HTML) -- the inverse of turndown. It passes marked's own CommonMark 0.31.2 and GFM 0.29 conformance suites in full and 98% of marked's `new/` regression specs (`tests/test_marked.py`), compared with the same html-differ semantics marked uses. Options mirror marked's (`gfm`, `breaks`, `pedantic`, `silent`, custom `renderer`); hooks, async, and third-party extensions are not ported. marked's ``\p{P}``/``\p{S}`` regex classes are baked from `unicodedata`, keeping the port dependency-free.

### preact

```python
from domonic.dom import document
from domonic_libs.preact import h, render, Component
from domonic_libs.preact.hooks import useState, useEffect

def Greeting(props):
    return h("h1", None, "Hello ", props["name"])

root = document.createElement("div")
render(h(Greeting, {"name": "world"}), root)
str(root)  # '<div><h1>Hello world</h1></div>'
```

A file-for-file port of [Preact](https://github.com/preactjs/preact) 10.29.8 -- `create_element`/`h`, the vnode-diffing reconciler (keyed children with the skew algorithm, Fragments, refs, `dangerouslySetInnerHTML`), the `Component` class with the full lifecycle, `createContext`, and `preact/hooks` (as `domonic_libs.preact.hooks`) -- running against domonic's server-side DOM instead of a browser. There is no JSX, so `h` is the authoring API and lifecycle names keep their upstream camelCase. Rendering is synchronous (Preact's microtask batching is replaced by a flush at the end of each `render` or event handler); Suspense and `preact/compat` are not ported. `tests/test_preact.py` ports a cross-section of Preact's browser suite (render, components, keys, fragments, refs, context, hooks) to `unittest`.

### mermaid

```python
from domonic_libs.mermaid import render

svg = render("""flowchart TD
    A[Parse text] --> B{Diagram type?}
    B -->|sequence / pie| C[Direct renderer]
    B -->|flowchart| D[dagre layout]
    C --> E[Emit SVG]
    D --> E
    E --> F((domonic tree))""")
# -> '<svg class="mermaid flowchart" viewBox="0 0 ..." ...>...</svg>'
```

A port of [Mermaid](https://github.com/mermaid-js/mermaid) (mermaid@11.9.0) that turns diagram text into a domonic SVG tree -- no `mermaid.js` bundle, no headless browser, no Graphviz binary. `render(text)` auto-detects the type; the CLI is `dlx mermaid`.

| diagram | status |
| --- | --- |
| **sequence** | grammar + `SequenceDB` + renderer: participants (box and actor glyph), lifelines, the full arrow set, self-message curves, notes, activation bars, and the `loop` / `alt` / `opt` / `par` / `critical` / `break` / `rect` box machinery (nested boxes grow to enclose their contents). Gaps: `box` groups, autonumber badges, KaTeX, wrapping |
| **pie** | slices, percentages, legend, `showData` -- over domonic's `d3.shape` (`pie`/`arc`) and `d3.scale` |
| **timeline** | sections, periods, events, the activity line, wrapped node text |
| **flowchart** / `graph` | node shapes, the arrow zoo (labels, lengths, `--x` / `--o`), `&` groups, chains, `subgraph`; laid out by the bundled **dagre** port |

The sequence / pie / timeline parsers are checked against mermaid's own spec assertions (`tests/test_mermaid.py`); the flowchart parser is a pragmatic scanner for the common `flow.jison` subset (mermaid's is ~630 lines of stateful lexer), tested against hand-written cases. Text is measured through domonic's real `getBBox()` -- a gap this port surfaced, [since implemented in domonic 1.5.0](docs/domonic-wrinkles.md#resolved-in-domonic-150). `examples/mermaid_demo.py` is a live workbench.

### dagre

```python
from domonic_libs.dagre import Graph, layout

g = Graph({"compound": True})
g.setGraph({"rankdir": "LR", "nodesep": 40, "ranksep": 60})
g.setDefaultEdgeLabel(lambda *a: {})
for v in "abc":
    g.setNode(v, {"width": 80, "height": 30})
g.setEdge("a", "b", {}); g.setEdge("a", "c", {})
layout(g)
g.node("b")            # {'x': ..., 'y': ..., 'rank': ..., ...}
g.edge("a", "b")["points"]
```

A faithful file-for-file port of [dagre](https://github.com/dagrejs/dagre) and the slice of [graphlib](https://github.com/dagrejs/graphlib) it needs -- directed-graph hierarchical layout, no C or JS dependency. The whole pipeline is ported: greedy-FAS acyclic → Sander nesting graph → network-simplex rank → barycenter + Barth bilayer crossing minimisation → Brandes-Köpf x-coordinates → edge routing. Used by the Mermaid flowchart renderer, and usable on its own for any layered-graph drawing (`dlx dagre` takes an edge list). Per-cluster `rankdir` recursion is the one omission; `tests/test_dagre.py` does structural/invariant checks.

## App Wrapper

Install `.[app]` or `.[examples]` before using this part.

```python
from domonic.events import Event
from domonic.html import button, h1, main

from domonic_libs import App, on


app = App("Hello")


def clicked(event):
    print(event.type)


@app.route("/")
def index():
    return main(h1("Hello"), on(button("Click me"), Event.CLICK, clicked))


app.run()
```

`App` is a thin bridge for domonic trees: routes return domonic HTML, callbacks receive domonic events, and examples can use OS file dialogs, menus, drag/drop, timers, storage, and transparent windows.

The render loop lives in a host-agnostic `BaseApp`. `App` is an alias for `DesktopApp`, which hosts it in a pywebview window. `BrowserApp` serves the same application to an ordinary browser over a small stdlib HTTP server -- the same route/handler code, no changes:

```python
from domonic_libs.app import BrowserApp

app = BrowserApp("Hello")

@app.route("/")
def index():
    return main(h1("Hello"), on(button("Click me"), Event.CLICK, clicked))

app.run(port=8000)   # serves http://127.0.0.1:8000/
```

Only the transport differs (pywebview's `js_api` vs `fetch`) and the native host (menus, dialogs, native drag/drop paths are desktop-only). Because the browser has no server-to-client push, `evaluate_js` / `refresh` on `BrowserApp` queue a command that rides back on the next event or timer response.

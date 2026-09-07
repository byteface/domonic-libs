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

Behaviours that trip up the ports are logged to feed back upstream: DOM ones in [docs/domonic-wrinkles.md](docs/domonic-wrinkles.md), and `domonic.javascript` (the JS runtime shim) ones in [docs/javascript-wrinkles.md](docs/javascript-wrinkles.md), driven by the acorn parser port.

## Install

To get the umbrella libraries like Mermaid, preact, turndown, marked, validator, qs, dompurify, readability etc...

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

The app wrapper API is in [docs/app.md](docs/app.md); the `dlx` CLI in [docs/cli.md](docs/cli.md). [`myjs`](#myjs) -- a JavaScript interpreter with an `ffi` bridge to native C -- ships as its own package (`pip install myjs`), built from `src/myjs/` via `packaging/myjs/`. [`htmlparser2`](#htmlparser2) also ships standalone (`pip install htmlparser2`), built from `src/htmlparser2/` via `packaging/htmlparser2/`. See [docs/myjs.md](docs/myjs.md), [docs/htmlparser2.md](docs/htmlparser2.md), and [docs/publishing.md](docs/publishing.md). Ported modules keep their upstream licenses -- see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

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

# Parse HTML with the htmlparser2 port
pipx inject domonic-libs htmlparser2
dlx htmlparse page.html --stats
cat page.html | dlx htmlparse --text

# Minify / format JavaScript -- pure Python, no Node (acorn parse -> generate)
dlx minify app.js -o app.min.js
cat src/*.js | dlx fmt --indent 2

# Transpile a Python subset to JavaScript (Python ast -> ESTree -> JS)
dlx pyjs script.py -o script.js

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

### htmlparser2

Standalone install:

```bash
pip install htmlparser2
htmlparser2 page.html --stats
```

```python
from htmlparser2 import DomUtils, Parser, parseDocument

events = []
Parser({
    "onopentag": lambda name, attrs, implied: events.append((name, attrs)),
    "ontext": lambda text: events.append(text),
}).end('<p class="lead">Hello &amp; welcome</p>')

doc = parseDocument("<ul><li>One<li>Two</ul>")
items = DomUtils.getElementsByTagName("li", doc)

# Let domonic.parseString use it as a backend.
from domonic import domonic
from htmlparser2 import install_domonic_parser

install_domonic_parser()
page = domonic.parseString("<main><h1>Hello</h1></main>", parser="htmlparser2")
```

A faithful-shape port of [htmlparser2](https://github.com/fb55/htmlparser2) -- callback parser, tokenizer state machine, domhandler, domutils traversal/query/stringify/mutation helpers, feed parser, implied-close rules, void elements, raw-text / RCDATA / plaintext parsing, and SVG/MathML casing rules. It builds domonic nodes directly. The first port leaned on `domonic.javascript.Map` / `Set`; the benchmarked hot tables now use native Python containers where the behaviour is equivalent.

On the CLI:

```bash
htmlparser2 page.html --stats
dlx htmlparse page.html              # parse and re-emit HTML
dlx htmlparse page.html --text       # textContent
dlx htmlparse page.html --stats      # node/type counts as JSON
dlx htmlparse page.html --domonic-backend
```

Benchmark it against domonic's parser backends:

```bash
./.venv/bin/python scripts/benchmark_htmlparser2.py ../projects/domonic/benchmarks/html_meaty_page.html --iterations 3
```

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

### acorn

```python
from domonic_libs.acorn import parse, generate, minify
from domonic_libs.acorn.jsx.transform import jsx_to_python
from domonic_libs.acorn.interpret import run_js

tree = parse("const f = x => x * 2", {"ecmaVersion": 2022})
tree.to_dict()      # {'type': 'Program', 'body': [{'type': 'VariableDeclaration', ...}], ...}
generate(tree)      # 'const f = x => x * 2;'   -- AST back to source
minify("app.js")    # read a file, return it whitespace-stripped

jsx_to_python("<div className='box'>{items}</div>")
# "div(items, _class='box')"

doc, log = run_js("const b = document.createElement('button');"
                  "b.textContent = 'Go'; document.body.appendChild(b);")
str(doc.body)  # '<body><button>Go</button></body>'
```

A faithful port of [acorn](https://github.com/acornjs/acorn) 8.18.0 (tokenizer, the `regexp.js` grammar validator, the recursive-descent parser) plus the [acorn-jsx](https://github.com/acornjs/acorn-jsx) plugin -- a pure-Python ECMAScript / JSX front end producing an ESTree tree. Its main job is stress-testing `domonic.javascript`; most of what it surfaced was fixed in domonic 1.6 and 1.7, and it keeps finding more ([docs/javascript-wrinkles.md](docs/javascript-wrinkles.md)).

- **`generate`** is the third leg -- `parse` reads JS, `interpret` runs an AST, `generate` writes an AST back out (`minify=True` strips whitespace; `indent=` sets the pretty width). It round-trips: `parse(generate(ast))` gives an equivalent tree, verified across the whole js262 + conformance corpus and real bundles (lodash, d3, vue, react, jquery, ...). On the CLI: `dlx minify app.js -o app.min.js` and `dlx fmt` -- a JavaScript minifier / formatter in pure Python, no Node.
- **`domonic_libs.pyjs`** goes the *other* way -- `transpile("def add(a,b): return a+b")` walks a CPython AST, translates it to ESTree, and emits JavaScript (via `generate`), with a `__py` runtime shim for the Python semantics JS doesn't share (container truthiness, `range`, negative indexing, `in`, `//`). A practical subset -- functions, classes, comprehensions, f-strings (with `:format` specs), generators, `try`/`except`, `import math` / `import random`, and the common builtins and `list`/`dict`/`set`/`str` methods. Python semantics are preserved where JS diverges: `//` and `%` floor, `==` / `<` compare containers element-wise, an integer-keyed dict becomes a `Map`. `dlx pyjs script.py -o script.js`. Every test transpiles Python, runs the JS through the interpreter, and asserts the output matches CPython. [examples/pyjs_app.py](examples/pyjs_app.py) and [examples/pyjs_canvas.py](examples/pyjs_canvas.py) write a whole interactive page / canvas animation in Python, inline the transpiled JS into one `.html` file, then drive it headlessly with `myjs.Page` to prove the DOM and canvas calls fire.
- **`jsx_to_python`** rewrites the JSX *markup* layer to `domonic.html` factories (or `h(...)` with `mode="h"`), passing JS expressions inside `{ ... }` through verbatim.
- **`interpret.run_js`** is a tree-walking evaluator for the practical subset of ECMAScript -- expressions, functions + closures, control flow, objects / arrays, `this`, `new`, `class` (with `extends` / `super` / fields), and the JS coercion rules. It runs against the **whole** domonic runtime: the global object exposes ~190 constructors auto-collected from `domonic.javascript` / `domonic.webapi.*` / `domonic.dom` (`URL`, `Headers`, `Request` / `Response`, `Blob` / `FileReader`, `XMLHttpRequest`, `EventSource`, `Event` / `MouseEvent`, `MutationObserver` / `ResizeObserver` / `IntersectionObserver`, `Range` / `TreeWalker`, `DOMRect` / `DOMMatrix`, `XPathEvaluator`, `Path2D`, `FontFace`, `Notification`, `Worker`, …), forwards to domonic's real `window` for the rest (`location`, `navigator`, `atob`, `getComputedStyle`, `setTimeout`), and reaches the element surface directly -- `el.style` / `getComputedStyle` (CSSOM in `style.py`), `el.classList` / `el.dataset`, `el.addEventListener` + `dispatchEvent`. `console` and `document` are isolated per run; `document` also forwards to a real backing `Document` (`createComment`, `createEvent`, `evaluate`, …). `document.createElement(...).appendChild(...)` builds a real Python object tree. There is a pragmatic event loop -- `Promise`, `async` / `await`, `setTimeout`, `requestAnimationFrame` (which a headless `Page` steps with `.frames(n)`), `performance.now()` -- with microtasks ahead of timers, and ES module `import` / `export`. Generators, ES5-style prototype chains (`Foo.prototype.bar = ...`), `Symbol`, and getter/setter accessors all work; not covered: `Proxy`, `with`. Running real DOM scripts this way is a live stress test of `style.py`, `domonic.events`, `domonic.webapi`, and the DOM.

Thrown errors carry a `js_line` and a `js_trace` (call stack), and the `js_demo` workbench surfaces both.

Nothing here is exported from `import domonic_libs` (it stays lean). `examples/acorn_demo.py` (JS → ESTree / tokens), `examples/jsx_demo.py` (JSX → domonic Python, live-rendered), and `examples/js_demo.py` (JS run against the DOM) are workbenches.

### conformance

Three scorecards measure how close the JS + DOM layer is to spec, each a curated battery run end to end through the interpreter with a CI gate against a baseline:

- `python -m domonic_libs.conformance` — CSSOM / DOM assertions (`el.style` / `CSSStyleDeclaration`, `classList`, `dataset`, attribute reflection) modelled on Web Platform Tests → [docs/conformance.md](docs/conformance.md) (50/50).
- `python -m domonic_libs.js262` — a test262-style battery over language expressions / statements (closures, classes, generators, `async`/`await`, destructuring, modules) and the `Array` / `String` / `Object` / `Number` / `Math` / `JSON` / `Promise` / `RegExp` built-ins → [docs/js-compliance.md](docs/js-compliance.md) (175/175, 100%).
- `python -m domonic_libs.realworld` — real, unmodified, live-fetched npm library bundles (lodash, d3, zod, katex, luxon, ...) run through the interpreter and smoke-tested, the other half of the same methodology: feed it something huge and popular that nobody wrote with this interpreter in mind, and see what breaks → [docs/real-world.md](docs/real-world.md).

A failing check is an interpreter gap or a domonic gap; the message says which, and [docs/domonic-wrinkles.md](docs/domonic-wrinkles.md) / [docs/javascript-wrinkles.md](docs/javascript-wrinkles.md) track the domonic ones.

## myjs

`myjs` is a JavaScript interpreter packaged on top of the acorn port and its evaluator. It ships as **its own PyPI distribution** — `pip install myjs` (built from `src/myjs/` via `packaging/myjs/`, released in lockstep with `domonic-libs`; see [docs/publishing.md](docs/publishing.md)). `myjs` with no arguments starts a REPL; `myjs script.js` executes a file; `myjs page.html` renders an HTML page headlessly; `myjs -e "<code>"` evaluates a snippet.

```python
import myjs

myjs.eval("1 + 2 * 3")                 # -> 7
myjs.run("script.js")

s = myjs.Session()                     # isolated global scope
s.eval("const x = 21;"); s.eval("x * 2")   # -> 42

# headless HTML: parse a page, run its <script>s against a real DOM, drive it
page = myjs.Page.load("https://example.com/")    # a URL (fetches HTML + CSS + JS) or a local file
page.eval("getComputedStyle(document.body).color")   # the fetched CSS, applied
page.fill("#search", "widgets").submit("#form")
page.wait_for(".result")
page.text(".result")                            # like Puppeteer, no browser
myjs.render("index.html", strip_scripts=True)   # -> rendered HTML string
```

Scripts get the whole domonic DOM (`document`, `window`, ~190 constructors), an event loop (`Promise`, `async` / `await`, `setTimeout`), ES modules (`import` / `export`, with bare specifiers resolving to Python modules), a `WebSocket` client, a set of host bindings -- `fs`, `path`, `sh`, `http`, an asynchronous `fetch`, `os` (Node-flavoured), `process`, `say` / `notify` / `open`, and **`py`** for reaching into the entire Python ecosystem (`py.import("numpy")`) -- plus an **`ffi`** global that calls native C libraries through Python's `ctypes` -- no node-gyp, no C compiler:

```javascript
const libc = ffi.loadLibrary("c");
libc.abs.argtypes = [ffi.types.int];
libc.abs.restype  = ffi.types.int;
console.log(libc.abs(-42));            // 42

const buf = ffi.createStringBuffer(64);
libc.strcpy(buf, "written into C memory");
console.log(buf.value);
```

`ffi.loadLibrary` takes a short name (`"c"`, `"m"`), a path (`./libfoo.so`), or a macOS framework name; `ffi.createStringBuffer`, `ffi.callback` (wrap a JS function as a C function pointer), `ffi.cast` / `ffi.sizeof` / `ffi.string`, and the `ffi.types` table cover the rest. Thrown errors surface as `myjs.JSError` with `js_name` / `js_line` / `js_trace`. `myjs --gui app.js` renders the DOM the script builds in a native window (needs `[app]`).

Runnable tours — `myjs examples` lists all of them (`myjs examples <name> --run`): `wow.js` (the whole surface), `cockpit.js` (a live control center — dashboard, killable/respawnable workers, raw keypresses), `gpu.js` (zero-copy: a live numpy buffer's raw pointer becomes GPU texture data directly), `atoms.js` (a real website's real physics, fetched live and rendered with raylib), `hn.js` (Hacker News front page, live API + `Promise.all`), `sqlite.js` (SQL via `py.import("sqlite3")`), `words.js` (fetch a book, word-frequency table), `todo.js` (a real CLI tool), `chart.js` (an SVG bar chart via the DOM API), `async.js` (event loop, concurrent `Promise.all(fetch...)`), `realtime.js` (`WebSocket` + `setInterval`), `render.html` (headless render), `live.py` (hit a real live website — fetch its HTML + CSS + JS and run it), `automate.py` / `scrape.py` (drive or scrape a page's JS from Python — Puppeteer without a browser), `gui.js` (`--gui` window), `server.js` (a web server in JS), `ffi.js` (native C). Full reference: [docs/myjs.md](docs/myjs.md).

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

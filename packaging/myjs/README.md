# myjs

**A JavaScript interpreter for Python.** Run `.js` files, render HTML pages
headlessly, script the DOM, call native C through `ffi`, and reach the entire
Python ecosystem from JavaScript — no Node, no browser, no build step.

```bash
pip install myjs
# or, for an isolated CLI:
pipx install myjs
```

```bash
myjs                          # REPL (history, TAB completion, top-level await)
myjs script.js                # run a file
myjs script.js a b            # ...with ["a","b"] as globalThis.argv
myjs -e "6 * 7"               # evaluate a snippet
myjs page.html                # render a page headlessly -> HTML on stdout
myjs page.html -e "document.title"   # ...then read the rendered DOM
myjs examples                 # list the bundled demos; `myjs examples hn --run`
myjs examples cockpit --run   # a live TUI: dashboard, killable workers, raw keypresses
```

```python
import myjs

myjs.eval("1 + 2 * 3")               # -> 7
myjs.run("script.js")

s = myjs.Session()                   # an isolated global scope
s.eval("const x = 21;"); s.eval("x * 2")   # -> 42

# a .py file calling a .js file directly -- no bridge, no serialization
mod = myjs.import_js("math_utils.js")   # export function double(x) { return x*2; }
mod.double(21)                          # -> 42, a real Python call into real JS
```

## What a script can reach

| | |
| --- | --- |
| **DOM** | `document`, `window`, and ~190 constructors (`URL`, `Headers`, `Event`, `DOMRect`, `TextEncoder`, …). `document.createElement(...).appendChild(...)` builds a real tree. |
| **Event loop** | `Promise` (`all` / `allSettled` / `race` / `any` / `finally`), `async` / `await`, `setTimeout` / `setInterval`, `queueMicrotask`. Microtasks before timers. |
| **ES modules** | `import` / `export` from `.js` files; a bare specifier resolves to a Python module (`import np from "numpy"`). |
| **`fetch`** | asynchronous, thread-backed — `await Promise.all([fetch(a), fetch(b)])` is genuinely concurrent. `WebSocket` is a real RFC 6455 client. |
| **`fs` / `path` / `sh` / `http`** | read & write files (`fs.readBytes(path, n)` for a raw header), run shell commands, serve HTTP (`http.serve(port, handler)`). |
| **`struct`** | pre-imported — `struct.unpack_from(fmt, fs.readBytes(path, n))` reads a BMP/PNG/ELF header with no library. |
| **`os` / `process`** | Node-flavoured — `os.platform()`, `os.cpus()`, `process.argv`, `process.env`, `process.exit()`. |
| **`ffi`** | call any C library through `ctypes` — no node-gyp, no compiler. |
| **`py`** | **callable** — `py("2 ** 10")` evaluates Python; `py.import("pandas")`, `py.exec(...)`. The whole package index. |
| **`console`** | `%s` / `%d` / `%c` format specifiers, `console.table`, `console.group`, `console.count` / `time` / `assert`. |
| **native dialogs** | `prompt()` / `confirm()` / `chooseFile()` / `chooseFolder()` — the real macOS UI, driven from JS. |
| **`clipboard`** | `readText()` / `writeText()` — the real system clipboard, shared with every other app. |
| plus | `say` / `notify` / `open`, `hash`, `atob` / `btoa`, `localStorage` |

```javascript
const libc = ffi.loadLibrary("c");
libc.abs.argtypes = [ffi.types.int];
libc.abs.restype  = ffi.types.int;
libc.abs(-42);                              // 42

const rows = py.import("sqlite3").connect(":memory:").execute("SELECT 1+1").fetchall();
console.table([...py.list(py.list(rows)[0])]);
```

## Headless HTML — render, scrape, automate

```python
page = myjs.Page.load("https://example.com/")   # a URL (fetches HTML + CSS + JS) or a local file
page.eval("getComputedStyle(document.body).color")   # the fetched CSS, applied
page.fill("#search", "widgets")
page.submit("#form")
page.wait_for(".result")                # pump the event loop until it appears
page.text(".result")                    # read it back

myjs.render("app.html", strip_scripts=True)   # SSR: one call -> rendered HTML
```

`Page.load` takes a local path or an `http(s)://` URL. For a URL it fetches the
page, every `<link rel=stylesheet>` (folded into the document so
`getComputedStyle` sees the rules), and every `<script src>` — all resolved
relative to the page URL. `<script type="module">` gets module semantics;
`DOMContentLoaded` / `load` fire. It's Puppeteer without a browser — a
`pip install`, not a 150 MB Chromium download.

## Command line

```
myjs [FILE] [ARGS...]           run a .js file (ARGS -> globalThis.argv),
                                or render a .html file headlessly
  -e, --eval JS                 evaluate JS; with a .html file, against the page
  -o, --output FILE             write rendered HTML to a file
  --html                        force headless-render mode
  --strip-scripts               drop <script> elements after they run
  --gui                         show the resulting DOM in a native window (needs myjs[gui])
  -i, --interactive             enter the REPL after running
myjs examples [NAME] [--run]    list / view / run the bundled demos
myjs                            REPL
```

## The REPL

`readline` history (persisted to `~/.config/myjs/history`), reverse search, and
**TAB completion** of globals and `obj.member` chains. Multi-line input is
auto-detected; top-level `await` works. Values print the way a real REPL's
inspector would -- colored, wrapped past 72 columns, `Map`/`Set`/`RegExp`/
`Date`/`Symbol`/`Promise` shown natively rather than falling back to a generic
dump. A live `setInterval` dashboard redraws in place instead of flashing the
whole terminal. Commands: `.load <file>` (a `.js`, or a
`.html` rendered into the session as `page`), `.save`, `.editor`, `.clear`,
`.help`, `.exit`.

## Language embedding

```python
s = myjs.Session(scope={"answer": 42})
s.eval("answer * 2")                     # -> 84
```

A JS exception that escapes becomes `myjs.JSError` with `js_name`, `js_line`,
and `js_trace` (the call stack). Sessions are isolated; `console.log` output is
captured on `s.console_lines`.

The language layer passes a curated test262-style battery — closures, classes
(`extends` / `super` / fields / getters-setters / private / static),
destructuring, generators, labelled `break`, `async` / `await`, and the
`Array` / `String` / `Object` / `Number` / `Math` / `JSON` / `RegExp`
built-ins, real ES5-style prototype chains, and `Symbol`. Not covered: `Proxy`, `with`.

## How it's built

`myjs` is the runtime layer on top of the [`domonic-libs`](https://pypi.org/project/domonic-libs/)
`acorn` port — a faithful Python port of the [acorn](https://github.com/acornjs/acorn)
parser, a tree-walking evaluator, and a code generator (`parse` / `interpret` /
`generate`, so JS can go source → AST → source) — running on
[`domonic`](https://pypi.org/project/domonic/)'s DOM. It ships in lockstep with `domonic-libs`.

Full reference: **[docs/myjs.md](https://github.com/byteface/domonic-libs/blob/master/docs/myjs.md)**.
MIT licensed.

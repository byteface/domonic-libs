# myjs

A JavaScript interpreter for Python, packaged on top of the acorn port (`domonic_libs.acorn`) and its tree-walking evaluator. It runs a practical subset of ECMAScript against domonic's server-side DOM, renders HTML pages headlessly, and hands scripts an `ffi` global for calling native C libraries through Python's `ctypes`.

`myjs` is its own PyPI package -- `pip install myjs` -- and its own top-level import.

## Command line

```
myjs                 start a REPL
myjs script.js       execute a .js file
myjs page.html       render a .html file headlessly (run its <script>s, print the HTML)
myjs page.html -e J  render, then evaluate J against the page (scraping / assertions)
myjs -e "6 * 7"      evaluate a snippet and print the result
myjs script.js a b   execute, with ["a", "b"] as globalThis.argv
myjs script.js -i    run, then drop into the REPL
myjs page.html --strip-scripts -o out.html   render a static snapshot to a file
myjs app.js --gui    run, then show the resulting DOM in a native window
```

A file ending `.html` / `.htm` renders headlessly (force it for other names with `--html`). `--gui` needs pywebview (`pip install "myjs[gui]"`).

The REPL keeps one global scope and exposes `_` as the last result. With `readline` it has persistent history (`~/.config/myjs/history`), line editing, reverse search, and **TAB completion** of globals and `obj.member` chains. Multi-line input is auto-detected (unclosed brackets / template literals / a trailing operator). Top-level `await` works. Values print the way a real REPL's inspector would -- colored, wrapped past 72 columns, `Map`/`Set`/`RegExp`/`Date`/`Symbol`/`Promise` shown natively (`Map(1) { 'k' => 'v' }`, `/abc/gi`, `Promise { 42 }`, ...), not a generic fallback. A live `setInterval` dashboard (`console.clear()` on every tick) redraws in place instead of flashing the whole terminal. Commands:

| | |
| --- | --- |
| `.load <file>` | run a `.js` file, or render a `.html` file into the session as `page` |
| `.save [file]` | write the input history to a file |
| `.editor` | multi-line paste mode (end with a blank line) |
| `.clear` | fresh session | `.help` · `.exit` |

## Python API

```python
import myjs

myjs.eval("1 + 2 * 3")          # -> 7   (module-level, shared session)
myjs.run("script.js")           # -> the file's completion value

s = myjs.Session()              # an isolated global scope
s.eval("const x = 21;")
s.eval("x * 2")                 # -> 42
s.console_lines                 # captured console.log output
s.document                      # the domonic Document the script built
```

`eval` accepts a `scope=` dict to inject extra globals (a throwaway session is used when it is given). A JavaScript exception that escapes becomes a `myjs.JSError` with `js_name`, `js_line`, and `js_trace` (the call stack).

### Calling JS from Python

A JS function is a real, callable Python object -- no bridge, no serialization needed to call one from a `.py` file:

```python
# math_utils.js: export function double(x) { return x * 2; }
mod = myjs.import_js("math_utils.js")
mod.double(21)          # -> 42, a real Python call into a real JS function
mod["double"](21)       # -> 42, same object either way (dict access also works)
```

`import_js` runs the file and returns its `export`ed names as a `Session.exports` object. `myjs.run("file.js")` still works the old way too (returns the file's completion value, not its exports) -- `import_js` is for when you want to reach into what a module actually exports. `examples/myjs/from_python.py` is a runnable tour.

## Headless HTML rendering

```python
import myjs

page = myjs.Page.load("index.html")              # a local file...
page = myjs.Page.load("https://example.com/")    # ...or a live URL

page.title                              # the <title> after scripts ran
page.query("h1").textContent            # inspect the rendered DOM (domonic elements)
page.query_all(".item")
page.eval("getComputedStyle(document.body).color")   # the fetched CSS, applied
page.eval("document.querySelectorAll('li').length")   # poke at the page's JS state
page.serialize()                        # the HTML after the scripts ran
page.errors                             # list[JSError] -- scripts that threw

myjs.render("index.html", strip_scripts=True)   # one call -> rendered HTML string
```

`Page.load` takes a local path or an `http(s)://` URL. For a URL it fetches the page, fetches every `<link rel="stylesheet">` and folds the rules into the document (so `getComputedStyle` sees them -- inline `<style>` already worked), and fetches every `<script src>`, all resolved relative to the page URL. Scripts run in one shared global scope with the real domonic DOM as `document` / `window`; `<script type="module">` gets module semantics (relative `import`, and bare specifiers resolve to Python modules); non-JS `type`s are skipped. `DOMContentLoaded` and `load` fire after, and the event loop drains. `Page(html_string, base_dir=..., url=...)` takes source directly; `css=False` skips stylesheet fetching. `location` inside the page reflects the `url`. `fetch`, `Promise`, `setTimeout`, `localStorage`, `WebSocket` all work inside page scripts.

### Driving the page (headless automation)

```python
page = myjs.Page.load("todo.html")
page.fill("#new-todo", "buy milk")
page.submit("#form")                      # or page.click("#add")
page.wait_for(".todo-item")               # pump the loop until it appears
page.click(page.query_all(".todo-item")[0])   # click a selector or an element
page.text(".count")                       # "1 item"
```

| method | |
| --- | --- |
| `click(sel_or_el)`, `click_all(sel)` | fire `click` (via `element.click()`) |
| `fill(sel, value)` | set `.value`, fire `input` + `change` |
| `check(sel[, checked])`, `select_option(sel, value)`, `submit(sel)` | form controls |
| `wait_for(sel, timeout=5)`, `wait(seconds)` | pump the loop until a condition / for a duration |
| `text(sel)`, `value(sel)`, `attr(sel, name)`, `inner_html(sel)` | read |
| `exists(sel)`, `count(sel)`, `query(sel)`, `query_all(sel)` | query |

Use it for server-side rendering, scraping JS-built pages, static-site generation (`strip_scripts=True`), or end-to-end testing a page's behaviour without a browser.

## console

Beyond `log` / `info` / `debug` / `warn` / `error`: `%s` / `%d` / `%i` / `%f` / `%o` / `%c` format specifiers, `console.group` / `groupEnd` (indents), `console.table`, `console.count` / `countReset`, `console.time` / `timeEnd`, `console.assert`, `console.dir`, `console.clear`. From the CLI, `error` / `warn` / `assert` go to stderr.

## What a script can reach

* **The DOM** — `document`, `window`, and ~190 constructors auto-collected from `domonic.javascript` / `domonic.webapi.*` / `domonic.dom` (`URL`, `Headers`, `Event`, `DOMRect`, …). `document.createElement(...).appendChild(...)` builds a real Python object tree.
* **`ffi`** — native C libraries via `ctypes` (below).
* **Host bindings** — everything in the next section.
* **An event loop** — `Promise`, `async` / `await`, `setTimeout` / `setInterval` / `clearTimeout`, `queueMicrotask`.
* **ES modules** — `import` / `export` from `.js` files, and bare specifiers resolve to Python modules.
* **`WebSocket`** — a real RFC 6455 client (`.onopen` / `.onmessage` / `.onclose`, `.send`, `.close`).

Generators, ES5-style prototype chains (`Foo.prototype.bar = ...`), `Symbol`, and getter/setter accessors all work; not covered: `Proxy`, `with`.

## ES modules

Scripts run as modules when they contain a top-level `import` / `export` (or end in `.mjs`).

```javascript
// lib.js
export const TAU = 6.28;
export function double(x) { return x * 2; }
export default (x) => x * x;

// app.js
import square, { TAU, double } from "./lib.js";
import * as lib from "./lib.js";
import np from "numpy";                 // a bare specifier -> a Python module
```

Relative paths (`./`, `../`, `/`) load `.js` / `.mjs` / `dir/index.js`; modules execute once and are cached; cycles are tolerated (a partially-populated namespace). Bindings are snapshots, not live. A **bare specifier** imports a Python module — its public attributes become named exports and the module itself is the default export.

## WebSocket

```javascript
const ws = new WebSocket("wss://ws.postman-echo.com/raw");
ws.onopen = () => ws.send("hello");
ws.onmessage = (e) => { console.log(e.data); ws.close(); };
ws.onclose = () => console.log("closed");
```

A dependency-free client: HTTP Upgrade handshake, client-masked frames, ping/pong, text and binary messages, `wss://` via TLS. Events dispatch on the event loop. `examples/myjs/realtime.js` is a tour.

## async / await

There is a real event loop. `Promise` (with `.then` / `.catch` / `.finally` and `Promise.resolve` / `reject` / `all` / `allSettled` / `race` / `any`), `async` functions, `await`, and the timer functions all work, microtasks run before timers, and top-level `await` is allowed.

```javascript
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  await wait(100);
  // fetch is asynchronous and runs on a background thread -- these three
  // requests happen concurrently, not one after another
  const [a, b, c] = await Promise.all([
    fetch("https://api.github.com/users/torvalds"),
    fetch("https://api.github.com/users/gvanrossum"),
    fetch("https://api.github.com/users/byteface"),
  ]);
  console.log(a.json().public_repos, b.json().public_repos, c.json().public_repos);
}
main();
```

`examples/myjs/async.js` is the full tour. Two simplifications versus a spec engine: `async` functions run to completion when first called (`await` pumps the loop inline) rather than suspending at the first `await`, so ordering between an async function's body and code right after its call site is eager; and `fetchSync` / `sh` / `Response.json()` stay synchronous (calling `await` on their non-promise result is a harmless no-op).

## Host bindings

All synchronous. Handed to every script as globals; `require("fs")` etc. also work, and `require("<anything>")` falls through to importing a Python module.

| Global | What it does |
| --- | --- |
| `fs` | `readFileSync`, `readBytes(path, n?, offset?)`, `writeFileSync` (accepts a string, or real binary data — a `Uint8Array` / Python `bytes`), `appendFileSync`, `existsSync`, `readdirSync`, `mkdirSync`, `rmSync`, `renameSync`, `copyFileSync`, `statSync`, `realpathSync`, `cwd` |
| `path` | `join`, `dirname`, `basename`, `extname`, `resolve`, `sep` |
| `sh(cmd, {cwd, timeout})` | run a shell command → `{stdout, stderr, code, ok}`; also `.trim()`, `.json()`, `.lines()` |
| `http` | `http.get(url)`, `http.post(url, body)`, `http.request(url, opts)` (all synchronous), `http.serve(port, handler)` |
| `fetch(url, opts)` | **asynchronous** — returns a `Promise<Response>`, request runs on a background thread; `Response` has `.status`, `.ok`, `.headers`, `.text()`, `.json()`, `.bytes()`. `fetchSync` is the blocking version. |
| `WebSocket(url)` | RFC 6455 client — `.onopen` / `.onmessage` / `.onclose` / `.onerror`, `.send()`, `.close()`, `.addEventListener` |
| `os` | Node-flavoured: `platform()`, `arch()`, `type()`, `release()`, `hostname()`, `homedir()`, `tmpdir()`, `cpus()`, `totalmem()`, `userInfo()`, `EOL` |
| `process` | `argv`, `env`, `platform`, `arch`, `pid`, `cwd()`, `chdir()`, `exit(code)` |
| `py` | **callable** — `py("2 ** 10")` evaluates a Python expression; plus `py.import("numpy")`, `py.exec("stmts")`, `py.eval`, `py.list(it)` → JS array, `py.dict`, `py.dir`, `py.type`, `py.getattr` — the whole Python ecosystem |
| `struct` | Python's `struct` module, pre-imported — `pack`, `unpack`, `unpack_from`, `calcsize` for binary file headers |
| `say(text)` | text-to-speech (`say` on macOS, `espeak` on Linux) |
| `notify(text, title)` / `alert(text, title)` | native notification / dialog (macOS `osascript`, Linux `notify-send`) |
| `prompt(text, default)` / `confirm(text)` | native OS input / Yes-Cancel dialog (macOS `osascript`; falls back to stdin elsewhere) |
| `chooseFile()` / `chooseFolder()` | the real Finder picker (macOS); `None` off-macOS or on Cancel |
| `clipboard.readText()` / `.writeText(s)` | the real system clipboard (`pbcopy`/`pbpaste`, `xclip`/`xsel`/`wl-copy`, `clip`/PowerShell) |
| `open(target)` | open a file or URL in the default app |
| `hash` | `hash.md5(s)`, `hash.sha256(s)` |
| `atob` / `btoa` | base64 |
| `sleep(seconds)`, `now()` | timing |

`http.serve` blocks until Ctrl-C; the handler is a JS function `(req) => string | {status, headers, body}` where `req` is `{method, path, headers, body}`. `examples/myjs/server.js` is a web server whose HTML is built with `document.createElement`.

### py — reaching into Python

`py` is callable — `py("<expression>")` evaluates Python and returns the value; if the code is a statement (or block), it falls back to `exec` and returns the resulting namespace:

```javascript
py("2 ** 10");                            // 1024
py("sorted([3, 1, 2])");                  // [1, 2, 3]
py("print('from python')");              // prints, returns null
py.exec("import math\nr = math.hypot(3, 4)").r;   // 5
```

`py.import(name)` returns the live module; attribute access, calls, and iteration go through the interpreter's normal Python fall-through, so most things just work:

```javascript
const stats = py.import("statistics");
stats.mean([2, 4, 6, 8]);                 // 5

const np = py.import("numpy");             // if pip-installed
Array.from(np.linspace(0, 1, 5));

py.list(py.import("itertools").islice([10, 20, 30, 40], 2));   // [10, 20]
```

Also `py.dir(o)`, `py.type(o)`, `py.getattr(o, name)`, `py.repr(o)`, `py.globals()`. JS strings passed to Python are plain `str`; values coming back are marshalled where obvious (`list`/`tuple` → JS array, `dict` → object). Python `bytes` stay `bytes` — call `.decode()` on them.

## ffi — calling native C

```javascript
const libc = ffi.libc();                   // resolves libc.so.6 / libSystem.dylib / msvcrt for you
const abs_ = libc.fn("abs", "int", ["int"]);   // one-line argtypes + restype
abs_(-42);                                  // 42

// the longer, explicit form still works (and is what .fn() does for you):
libc.abs.argtypes = [ffi.types.int];
libc.abs.restype  = ffi.types.int;
libc.abs(-42);                              // 42
```

| API | Purpose |
| --- | --- |
| `ffi.loadLibrary(name)` | `"c"` / `"m"`, `./libfoo.so`, or `CoreFoundation` on macOS; `"c"`/`"m"` resolve correctly on Linux, macOS, *and* Windows (`msvcrt`) |
| `ffi.libc()` / `ffi.libm()` | shorthand for `ffi.loadLibrary("c")` / `("m")` |
| `lib.<symbol>` | a callable C function; set `.argtypes` / `.restype` / `.errcheck` |
| `lib.fn(name, restype, argtypes)` | resolve + declare in one call — types as `ffi.types.x` or a plain string (`"double"`, `"int"`, `"string"`, ...) |
| `ffi.types` | `int`, `uint`, `long`, `size_t`, `double`, `float`, `bool`, `char`, `string` (`char*`), `wstring`, `pointer`, the sized `int8`…`uint64`, `void` |
| `ffi.createStringBuffer(str \| size)` | a mutable buffer; `.value` (str), `.raw` (bytes), `.length` |
| `ffi.callback(restype, [argtypes], fn)` | wrap a JS function as a C function pointer (`CFUNCTYPE`) |
| `ffi.cast(v, type)`, `ffi.sizeof(type)`, `ffi.string(ptr)` | pointer helpers |
| `ffi.addressof(buf)`, `ffi.pointer`, `ffi.byref`, `ffi.errno()` | lower-level ctypes access |

Strings passed to C are encoded UTF-8; `char*` return values are decoded back to JS strings. A `Buffer` passes its underlying storage straight through, so `libc.strcpy(buf, "text")` mutates it in place.

`argtypes`/`restype` still have to be declared once per function -- there's no reliable way to *infer* them from a call site. A whole-number JS value (`11`) can't tell you whether the C function wants an `int` or a `double`; that's an ABI fact about the function (which register convention it expects), invisible from the argument alone. `.fn()` removes the boilerplate, not the declaration.

`examples/myjs/ffi.js` is a runnable tour (`myjs examples/myjs/ffi.js`).

## Examples

All bundled in the package — `myjs examples` lists them, `myjs examples <name>` prints one, `myjs examples <name> --run` runs it.

| File | Shows |
| --- | --- |
| `cockpit.js` | an interactive live control center — dashboard, killable/respawnable workers, raw keypresses, clipboard, SIGINT-safe |
| `wow.js` | the whole surface in one script — machine info, shell, files, `py`, live `fetch`, C, DOM-to-disk, `notify` |
| `sysmon.js` | a live CPU/memory/disk/battery dashboard, straight off the real OS |
| `parallel.js` | real OS threads — hash buffers in parallel via Python's `threading`, measure the actual speedup |
| `procstream.js` | spawn a child process, stream its output live, kill it early |
| `filewatch.js` | a directory watcher (no chokidar) while a real background thread edits files |
| `dialogs.js` | the OS's own UI from JS — `prompt`/`confirm`/`chooseFile`/`chooseFolder` |
| `clipboard.js` | read and write the real system clipboard |
| `wav.js` | synthesize audio with JS math, pack real PCM16 bytes, let the OS play it |
| `bmp.js` | read a real binary file header with `struct` and `fs.readBytes` |
| `snapshot.js` | turn a DOM-described scene into a real, valid image file |
| `flask.js` | a real Flask app — route handlers written as plain JS functions (needs `pip install flask`) |
| `raylib.js` | a real native window (raylib via `ffi`) — a button wired to a JS `onclick` (needs `brew install raylib`) |
| `gpu.js` | zero-copy: a live numpy buffer's raw pointer becomes GPU texture data directly (needs raylib + numpy) |
| `atoms.js` | a real website's real physics, fetched live and run unmodified, rendered with raylib (needs `brew install raylib`) |
| `from_python.py` / `greet.js` | a `.py` file importing a `.js` file and calling its exports directly, no bridge |
| `syscall.js` | the raw `uname(2)` syscall via `ffi` — no `os`/`platform` module involved |
| `procs.js` | a native process table — `ps(1)`'s real numbers, sorted and rendered in JS |
| `signals.js` | spawn a child process, send it a real SIGTERM, watch it trap and shut down |
| `hn.js` | Hacker News front page in the terminal — live API, `Promise.all` concurrency |
| `sqlite.js` | SQL from JavaScript — in-memory SQLite via `py.import("sqlite3")`, `console.table` |
| `words.js` | fetch a book, word-frequency with `Map` + regex, top-15 table |
| `todo.js` | a real CLI tool — `argv`, `fs`, JSON persistence, `console.table` |
| `chart.js` | build an SVG bar chart with the DOM API, write it, `open()` it |
| `async.js` | event loop, `async` / `await`, concurrent `Promise.all(fetch...)`, `Promise.race` |
| `realtime.js` | `WebSocket` + `setInterval` against a live echo server |
| `gui.js` | build a UI with the DOM API; `myjs --gui` opens it in a window |
| `server.js` | a web server in JS, HTML built with `document.createElement` |
| `render.html` | headless render — `<script type=module>` + relative import builds a report table (`myjs examples/myjs/render.html --strip-scripts`) |
| `automate.py` | drive a page's JS from Python — fill / submit / click / wait, like Puppeteer without a browser |
| `scrape.py` | render a SPA headlessly, pull the DOM out as JSON |
| `live.py` | hit a real live website — fetch its HTML + CSS + JS and run it (`python examples/myjs/live.py [url]`) |
| `ffi.js` | native C via `ffi` |

Source lives under [`examples/myjs/`](https://github.com/byteface/domonic-libs/tree/master/examples/myjs).

## Roadmap

A Python-hosted JS interpreter with direct native + ecosystem reach and a headless DOM. Next: a live `--gui` mode (JS ↔ window round-trips, not just a one-shot render), streaming HTTP and `ReadableStream`, a WebSocket *server* to pair with `http.serve`, `localStorage` / `fetch` inside headless pages, and more of the Web API surface.

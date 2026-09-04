# myjs

A standalone JavaScript interpreter, packaged on top of the acorn port (`domonic_libs.acorn`) and its tree-walking evaluator. It runs a practical subset of ECMAScript against domonic's server-side DOM and hands scripts an `ffi` global for calling native C libraries through Python's `ctypes`.

`myjs` is its own top-level import (`import myjs`), installed with `domonic-libs`.

## Command line

```
myjs                 start a REPL
myjs script.js       execute a file
myjs script.js a b   execute, with ["a", "b"] as globalThis.argv
myjs -e "6 * 7"      evaluate a snippet and print the result
myjs script.js -i    run the file, then drop into the REPL
myjs --gui app.js    run, then show the DOM the script built in a native window
```

`--gui` needs pywebview (`pip install "domonic-libs[app]"`). The script builds a page with `document.createElement` / `document.title`; the window renders it.

The REPL keeps one global scope, handles multi-line input, exposes `_` as the last result, and understands `.exit` / `.clear` / `.help`.

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

## What a script can reach

* **The DOM** — `document`, `window`, and ~190 constructors auto-collected from `domonic.javascript` / `domonic.webapi.*` / `domonic.dom` (`URL`, `Headers`, `Event`, `DOMRect`, …). `document.createElement(...).appendChild(...)` builds a real Python object tree.
* **`ffi`** — native C libraries via `ctypes` (below).
* **Host bindings** — everything in the next section.
* **An event loop** — `Promise`, `async` / `await`, `setTimeout` / `setInterval` / `clearTimeout`, `queueMicrotask`.
* **ES modules** — `import` / `export` from `.js` files, and bare specifiers resolve to Python modules.
* **`WebSocket`** — a real RFC 6455 client (`.onopen` / `.onmessage` / `.onclose`, `.send`, `.close`).

Not covered: generators, real prototype chains, `Proxy` / `Symbol` / accessors.

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

A dependency-free client: HTTP Upgrade handshake, client-masked frames, ping/pong, text and binary messages, `wss://` via TLS. Events dispatch on the event loop. `examples/myjs_realtime.js` is a tour.

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

`examples/myjs_async.js` is the full tour. Two simplifications versus a spec engine: `async` functions run to completion when first called (`await` pumps the loop inline) rather than suspending at the first `await`, so ordering between an async function's body and code right after its call site is eager; and `fetchSync` / `sh` / `Response.json()` stay synchronous (calling `await` on their non-promise result is a harmless no-op).

## Host bindings

All synchronous. Handed to every script as globals; `require("fs")` etc. also work, and `require("<anything>")` falls through to importing a Python module.

| Global | What it does |
| --- | --- |
| `fs` | `readFileSync`, `writeFileSync`, `appendFileSync`, `existsSync`, `readdirSync`, `mkdirSync`, `rmSync`, `renameSync`, `copyFileSync`, `statSync`, `realpathSync`, `cwd` |
| `path` | `join`, `dirname`, `basename`, `extname`, `resolve`, `sep` |
| `sh(cmd, {cwd, timeout})` | run a shell command → `{stdout, stderr, code, ok}`; also `.trim()`, `.json()`, `.lines()` |
| `http` | `http.get(url)`, `http.post(url, body)`, `http.request(url, opts)` (all synchronous), `http.serve(port, handler)` |
| `fetch(url, opts)` | **asynchronous** — returns a `Promise<Response>`, request runs on a background thread; `Response` has `.status`, `.ok`, `.headers`, `.text`, `.json()`, `.bytes()`. `fetchSync` is the blocking version. |
| `WebSocket(url)` | RFC 6455 client — `.onopen` / `.onmessage` / `.onclose` / `.onerror`, `.send()`, `.close()`, `.addEventListener` |
| `os` | Node-flavoured: `platform()`, `arch()`, `type()`, `release()`, `hostname()`, `homedir()`, `tmpdir()`, `cpus()`, `totalmem()`, `userInfo()`, `EOL` |
| `process` | `argv`, `env`, `platform`, `arch`, `pid`, `cwd()`, `chdir()`, `exit(code)` |
| `py` | `py.import("numpy")`, `py.eval("...")`, `py.list(it)` → JS array, `py.dict(o)`, `py.repr`, `py.dir`, `py.type` — the whole Python ecosystem |
| `say(text)` | text-to-speech (`say` on macOS, `espeak` on Linux) |
| `notify(text, title)` / `alert(text, title)` | native notification / dialog (macOS `osascript`, Linux `notify-send`) |
| `open(target)` | open a file or URL in the default app |
| `hash` | `hash.md5(s)`, `hash.sha256(s)` |
| `atob` / `btoa` | base64 |
| `sleep(seconds)`, `now()` | timing |

`http.serve` blocks until Ctrl-C; the handler is a JS function `(req) => string | {status, headers, body}` where `req` is `{method, path, headers, body}`. `examples/myjs_server.js` is a web server whose HTML is built with `document.createElement`.

### py — reaching into Python

`py.import(name)` returns the live module; attribute access, calls, and iteration go through the interpreter's normal Python fall-through, so most things just work:

```javascript
const stats = py.import("statistics");
stats.mean([2, 4, 6, 8]);                 // 5

const np = py.import("numpy");             // if pip-installed
Array.from(np.linspace(0, 1, 5));

py.list(py.import("itertools").islice([10, 20, 30, 40], 2));   // [10, 20]
```

JS strings passed to Python are plain `str`; values coming back are marshalled where obvious (`list`/`tuple` → JS array via `py.list`, `dict` → object). Python `bytes` stay `bytes` — call `.decode()` on them.

## ffi — calling native C

```javascript
const libc = ffi.loadLibrary("c");        // short name, path, or macOS framework
libc.abs.argtypes = [ffi.types.int];
libc.abs.restype  = ffi.types.int;
libc.abs(-42);                             // 42
```

| API | Purpose |
| --- | --- |
| `ffi.loadLibrary(name)` | `"c"` / `"m"`, `./libfoo.so`, or `CoreFoundation` on macOS |
| `lib.<symbol>` | a callable C function; set `.argtypes` / `.restype` / `.errcheck` |
| `ffi.types` | `int`, `uint`, `long`, `size_t`, `double`, `float`, `bool`, `char`, `string` (`char*`), `wstring`, `pointer`, the sized `int8`…`uint64`, `void` |
| `ffi.createStringBuffer(str \| size)` | a mutable buffer; `.value` (str), `.raw` (bytes), `.length` |
| `ffi.callback(restype, [argtypes], fn)` | wrap a JS function as a C function pointer (`CFUNCTYPE`) |
| `ffi.cast(v, type)`, `ffi.sizeof(type)`, `ffi.string(ptr)` | pointer helpers |
| `ffi.addressof(buf)`, `ffi.pointer`, `ffi.byref`, `ffi.errno()` | lower-level ctypes access |

Strings passed to C are encoded UTF-8; `char*` return values are decoded back to JS strings. A `Buffer` passes its underlying storage straight through, so `libc.strcpy(buf, "text")` mutates it in place.

`examples/myjs_ffi.js` is a runnable tour (`myjs examples/myjs_ffi.js`).

## Examples

| File | Shows |
| --- | --- |
| `examples/myjs_wow.js` | the whole surface in one script — machine info, shell, files, `py`, live `fetch`, C, DOM-to-disk, `notify` |
| `examples/myjs_async.js` | event loop, `async` / `await`, concurrent `Promise.all(fetch...)`, `Promise.race` |
| `examples/myjs_realtime.js` | `WebSocket` + `setInterval` against a live echo server |
| `examples/myjs_gui.js` | build a UI with the DOM API; `myjs --gui` opens it in a window |
| `examples/myjs_server.js` | a web server in JS, HTML built with `document.createElement` |
| `examples/myjs_ffi.js` | native C via `ffi` |

## Roadmap

A "hello world" for a Python-hosted JS interpreter with direct native and ecosystem reach. Next: generators, a live `--gui` mode (JS ↔ window round-trips, not just a one-shot render), streaming HTTP and `ReadableStream`, a WebSocket *server* to pair with `http.serve`, and more of the Web API surface.

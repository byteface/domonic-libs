# myjs

A JavaScript interpreter for Python. It runs a practical subset of ECMAScript against a server-side DOM, hands scripts an `ffi` bridge to native C libraries, and lets JavaScript reach the entire Python ecosystem.

```bash
pip install myjs
```

```bash
myjs                 # start a REPL
myjs script.js       # execute a file
myjs -e "6 * 7"      # evaluate a snippet
myjs --gui app.js    # run, then show the DOM the script built in a native window
```

```python
import myjs

myjs.eval("1 + 2 * 3")            # -> 7
myjs.run("script.js")

s = myjs.Session()                # an isolated global scope
s.eval("const x = 21;")
s.eval("x * 2")                   # -> 42
```

## What a script can reach

- **The DOM** — `document`, `window`, and ~190 constructors (`URL`, `Headers`, `Event`, `DOMRect`, …). `document.createElement(...).appendChild(...)` builds a real object tree.
- **An event loop** — `Promise` (with `all` / `allSettled` / `race` / `any`), `async` / `await`, `setTimeout` / `setInterval`, `queueMicrotask`. Microtasks run before timers.
- **ES modules** — `import` / `export` from `.js` files; a bare specifier resolves to a Python module.
- **`ffi`** — call native C libraries through `ctypes`, no compiler:

  ```javascript
  const libc = ffi.loadLibrary("c");
  libc.abs.argtypes = [ffi.types.int];
  libc.abs.restype  = ffi.types.int;
  libc.abs(-42);                       // 42
  ```

- **Host bindings** — `fs`, `path`, `sh` (shell), `http` + an async `fetch`, `os` (Node-flavoured), `process`, `WebSocket` (a real RFC 6455 client), `say` / `notify` / `open`, `hash`, `atob` / `btoa`.
- **`py`** — `py.import("numpy")`, `py.eval(...)`, `py.list(iter)` → the whole Python package index from JavaScript.

The language layer passes a curated test262-style battery: closures, classes (extends / super / fields / getters-setters / private / static), destructuring, generators, labelled break, `async` / `await`, and the `Array` / `String` / `Object` / `Number` / `Math` / `JSON` / `RegExp` built-ins. Not covered: real prototype chains, `Proxy` / `Symbol`, `with`.

## Language embedding

```python
s = myjs.Session(scope={"answer": 42})
s.eval("answer * 2")              # -> 84
```

A JavaScript exception that escapes becomes `myjs.JSError` with `js_name`, `js_line`, and `js_trace` (the call stack).

## How it is built

`myjs` is the runtime layer on top of the [`domonic-libs`](https://pypi.org/project/domonic-libs/) `acorn` port — a faithful Python port of the [acorn](https://github.com/acornjs/acorn) parser plus a tree-walking evaluator — which in turn runs on [`domonic`](https://pypi.org/project/domonic/)'s DOM. Full reference: [docs/myjs.md](https://github.com/byteface/domonic-libs/blob/master/docs/myjs.md).

MIT licensed.

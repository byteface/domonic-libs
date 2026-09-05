# myjs examples

Runnable demos. After `pip install myjs`, browse them with `myjs examples`
(and `myjs examples <name>` to view a file, `--run` to run it).

| | run | shows |
| --- | --- | --- |
| **cockpit.js** | `myjs examples/myjs/cockpit.js` | an interactive live control center — dashboard, killable/respawnable workers, raw keypresses, clipboard, SIGINT-safe |
| **wow.js** | `myjs examples/myjs/wow.js` | the whole surface in one script — machine info, shell, files, `py`, live `fetch`, native C, DOM→disk |
| **sysmon.js** | `myjs examples/myjs/sysmon.js` | a live CPU/memory/disk/battery dashboard, straight off the real OS |
| **parallel.js** | `myjs examples/myjs/parallel.js` | real OS threads: hash buffers in parallel via Python's `threading` and measure the actual speedup |
| **procstream.js** | `myjs examples/myjs/procstream.js` | spawn a child process, stream its output live, kill it early |
| **filewatch.js** | `myjs examples/myjs/filewatch.js` | a directory watcher (no chokidar) while a real background thread edits files |
| **dialogs.js** | `myjs examples/myjs/dialogs.js` | the OS's own UI from JS — `prompt`/`confirm`/`chooseFile`/`chooseFolder`, no `<input>` |
| **clipboard.js** | `myjs examples/myjs/clipboard.js` | read and write the real system clipboard |
| **wav.js** | `myjs examples/myjs/wav.js` | synthesize audio with JS math, pack real PCM16 bytes, let the OS play it |
| **bmp.js** | `myjs examples/myjs/bmp.js` | read a real binary file header with `struct` and `fs.readBytes` |
| **snapshot.js** | `myjs examples/myjs/snapshot.js` | turn a DOM-described scene into a real, valid image file |
| **flask.js** | `myjs examples/myjs/flask.js` | a real Flask app — route handlers written as plain JS functions (needs `pip install flask`) |
| **raylib.js** | `myjs examples/myjs/raylib.js` | a real native window (raylib via `ffi`) — a button wired to a JS `onclick` (needs `brew install raylib`) |
| **gpu.js** | `myjs examples/myjs/gpu.js` | zero-copy: a live numpy buffer's raw pointer becomes GPU texture data directly (needs raylib + numpy) |
| **atoms.js** | `myjs examples/myjs/atoms.js` | a real website's real physics, fetched live and run unmodified, rendered with raylib (needs `brew install raylib`) |
| **from_python.py** / **greet.js** | `python examples/myjs/from_python.py` | a `.py` file importing a `.js` file and calling its exports directly, no bridge |
| **syscall.js** | `myjs examples/myjs/syscall.js` | the raw `uname(2)` syscall via `ffi` — no `os`/`platform` module involved |
| **procs.js** | `myjs examples/myjs/procs.js` | a native process table — `ps(1)`'s real numbers, sorted and rendered in JS |
| **signals.js** | `myjs examples/myjs/signals.js` | spawn a child process, send it a real SIGTERM, watch it trap and shut down |
| **hn.js** | `myjs examples/myjs/hn.js` | Hacker News front page in the terminal — live API, `Promise.all` concurrency |
| **sqlite.js** | `myjs examples/myjs/sqlite.js` | SQL from JavaScript — in-memory SQLite via `py.import("sqlite3")`, `console.table` |
| **words.js** | `myjs examples/myjs/words.js` | fetch a book, word-frequency with `Map` + regex, top-15 table |
| **todo.js** | `myjs examples/myjs/todo.js add "task"` | a real CLI tool — `argv`, `fs`, JSON persistence, `console.table` |
| **chart.js** | `myjs examples/myjs/chart.js` | build an SVG bar chart with the DOM API, write it, `open()` it |
| **async.js** | `myjs examples/myjs/async.js` | the event loop — `async`/`await`, `Promise.all`/`race`, timers, microtask order |
| **realtime.js** | `myjs examples/myjs/realtime.js` | a hand-rolled RFC 6455 `WebSocket` client against a live echo server |
| **ffi.js** | `myjs examples/myjs/ffi.js` | call `libc` / `libm` directly through `ffi` (ctypes) |
| **server.js** | `myjs examples/myjs/server.js` | an HTTP server in JS whose pages are built with `document.createElement` |
| **gui.js** | `myjs --gui examples/myjs/gui.js` | build a UI with the DOM API; a native window renders it |
| **render.html** | `myjs examples/myjs/render.html --strip-scripts` | headless SSR — runs `<script type=module>` (+ a relative `import`) and prints the HTML |
| **automate.py** | `python examples/myjs/automate.py` | drive a page's JS from Python — fill / submit / click / wait, Puppeteer without a browser |
| **scrape.py** | `python examples/myjs/scrape.py` | render a SPA headlessly, pull the DOM out as JSON |
| **live.py** | `python examples/myjs/live.py [url]` | hit a real live website — fetch its HTML, its CSS (applied to `getComputedStyle`), and its JS, and run it |

`report-util.js` is a helper module imported by `render.html`.

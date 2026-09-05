"""Run real, unmodified, live-fetched JavaScript libraries through the
interpreter -- not a synthetic battery, the actual npm-published bundle real
developers use, smoke-tested with a few representative calls.

The point isn't spec coverage (that's what `js262`/`conformance` are for) --
it's the other half of the same "real-world sweep" methodology that already
found the sloppy-mode `this` bug, the ES5 prototype-chain bug, and the
`typeof Symbol`/`Object.prototype.toString` bug: feed the interpreter
something huge and popular that nobody wrote with myjs in mind, and see what
breaks. A failing row here is a genuine wrinkle candidate, exactly like a
failing row in `docs/conformance.md` is.

Two tiers of check:

* A curated few (the original 11) have a hand-written `suite/<name>.js` --
  real, representative API calls (`_.chunk(...)`, `dayjs(...).format(...)`,
  ...), same `test()`/`assert_equals()` harness as `conformance`.
* Everything else just needs to *load and expose something real* -- checked
  generically by diffing the global environment before/after evaluating the
  library, no hand-written assertions needed. Cheap to add hundreds more this
  way; still finds real load-time bugs, which is where most of the value
  turned out to be in practice (`d3`, `zod`, `mustache` were all found and
  fixed via load failures, not deep API mismatches).

``run_suite()`` fetches each library fresh over the network (deliberately not
vendored -- the point is testing against what's actually out there right now)
and returns a :class:`SuiteResult`; ``format_markdown()`` renders the
scorecard written to ``docs/real-world.md``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import signal
import urllib.error
import urllib.request
from pathlib import Path

from domonic_libs.acorn.interpret import Interpreter, JSThrow, default_globals
from domonic_libs.conformance.harness import HARNESS_JS

SUITE_DIR = Path(__file__).parent / "suite"

# name -> the real, live URL of that library's standalone browser bundle. No
# build step, no bundler -- exactly what a <script src> would load. The bare
# `jsdelivr.net/npm/<pkg>` form (no path) auto-resolves to whatever the
# package itself declares as its browser entry point.
_CURATED = {
    "lodash.js": "https://cdn.jsdelivr.net/npm/lodash@4.17.21/lodash.min.js",
    "dayjs.js": "https://cdn.jsdelivr.net/npm/dayjs@1.11.13/dayjs.min.js",
    "chroma.js": "https://cdn.jsdelivr.net/npm/chroma-js@2.4.2/chroma.min.js",
    "fuse.js": "https://cdn.jsdelivr.net/npm/fuse.js@7.0.0/dist/fuse.min.js",
    "papaparse.js": "https://cdn.jsdelivr.net/npm/papaparse@5.4.1/papaparse.min.js",
    "ramda.js": "https://cdn.jsdelivr.net/npm/ramda@0.30.1/dist/ramda.min.js",
    "mustache.js": "https://cdn.jsdelivr.net/npm/mustache@4.2.0/mustache.min.js",
    "handlebars.js": "https://cdn.jsdelivr.net/npm/handlebars@4.7.8/dist/handlebars.min.js",
    "zod.js": "https://cdn.jsdelivr.net/npm/zod@3.23.8/lib/index.umd.js",
    "d3.js": "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js",
    "katex.js": "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js",
}

# a further ~140 real npm packages, auto-resolved to their real browser
# bundle by jsdelivr -- no per-package path-guessing, deliberately broad
# rather than deep: functional/utility, dates, validation, templating,
# markdown/HTML, sanitization, data formats, crypto/hash, color, charts, math
# typesetting, numbers, animation, DOM/UI helpers, search, state machines,
# immutable data, events, async control flow, i18n, URL/UA parsing, strings,
# IDs, QR/barcode, zip/PDF, diff, assertions, physics/audio/3D, fonts,
# cookies, storage, equality/cloning, polyfills, encoding/compression,
# scroll/carousel/modal/toast UI widgets, table/grid, spreadsheet, PDF,
# queueing -- each picked to stress something a bit different, same spirit
# as why mermaid/acorn were ported.
_AUTO = [
    "underscore", "immer", "luxon", "yup", "superstruct", "ejs", "nunjucks",
    "marked", "showdown", "turndown", "dompurify", "sanitize-html", "xss", "he",
    "js-yaml", "fast-xml-parser", "ini", "crypto-js",
    "js-sha256", "bcryptjs", "tinycolor2", "culori", "chart.js",
    "echarts", "mathjs", "big.js", "decimal.js", "bignumber.js", "numeral",
    "accounting", "gsap", "animejs", "popmotion", "sortablejs", "dragula",
    "interactjs", "hammerjs", "tippy.js", "popper.js", "lunr", "minisearch",
    "xstate", "immutable", "eventemitter3", "mitt", "bluebird",
    "async", "rxjs", "i18next", "qs", "url-parse", "bowser",
    "platform", "ua-parser-js", "slugify", "pluralize", "voca", "striptags",
    "shortid", "seedrandom", "qrcode", "jsbarcode", "jszip", "file-saver",
    "jspdf", "diff", "fast-diff", "jsondiffpatch", "chai", "classnames",
    "clsx", "currency.js", "lru-cache", "matter-js", "howler", "three",
    "opentype.js", "js-cookie", "localforage", "deep-equal", "clone",
    "fast-deep-equal", "es6-promise", "modernizr", "js-base64", "pako",
    "canvas-confetti", "timeago.js", "semver", "axios", "clipboard", "markdown-it",
    # +50, added when the sweep grew from 108 to 158 libraries
    "moment", "date-fns", "spacetime", "joi", "ajv", "validator", "yaml",
    "commonmark", "cheerio", "csv-parse", "dot", "liquidjs", "squirrelly",
    "tocbot", "headroom.js", "aos", "typed.js", "swiper", "splide",
    "apexcharts", "c3", "cannon-es", "gl-matrix", "tone", "md5",
    "blueimp-md5", "jose", "buffer", "base64-js", "lz-string", "fflate",
    "ulid", "cuid", "polyglot", "navigo", "pubsub-js", "tiny-emitter",
    "p-queue", "p-retry", "seamless-immutable", "cleave.js", "muuri",
    "toastify-js", "sweetalert2", "notyf", "micromodal", "clipboard-copy",
    "party-js", "store2", "idb-keyval",
]

# packages whose bare `jsdelivr.net/npm/<pkg>` form 404s (no declared
# browser/main entry point jsdelivr can resolve to) -- a real, specific
# dist path in its place, same as any hand-pinned `_CURATED` entry.
_PINNED = {
    "uuid": "https://cdn.jsdelivr.net/npm/uuid@8.3.2/dist/umd/uuid.min.js",
    "nanoid": "https://cdn.jsdelivr.net/npm/nanoid@3.3.7/nanoid.js",
    "p-limit": "https://cdn.jsdelivr.net/npm/p-limit@3.1.0/index.js",
    "query-string": "https://cdn.jsdelivr.net/npm/query-string@8.1.0/index.js",
    "color": "https://cdn.jsdelivr.net/npm/color@4.2.3/index.js",
    "date-fns": "https://cdn.jsdelivr.net/npm/date-fns@3.6.0/cdn.min.js",
    "p-queue": "https://cdn.jsdelivr.net/npm/p-queue@8.0.1/dist/index.js",
    "p-retry": "https://cdn.jsdelivr.net/npm/p-retry@6.2.0/index.js",
    "splide": "https://cdn.jsdelivr.net/npm/@splidejs/splide@4.1.4/dist/js/splide.min.js",
    "polyglot": "https://cdn.jsdelivr.net/npm/node-polyglot@2.5.0/index.js",
}
_AUTO += list(_PINNED)

LIBRARY_URLS = dict(_CURATED)
LIBRARY_URLS.update({
    f"{pkg}.js": _PINNED.get(pkg, f"https://cdn.jsdelivr.net/npm/{pkg}")
    for pkg in _AUTO
})


@dataclasses.dataclass
class Case:
    name: str
    status: str  # "PASS" | "FAIL"
    message: str


@dataclasses.dataclass
class FileResult:
    filename: str
    cases: list[Case]
    error: str = ""  # set when the library failed to even load

    @property
    def passed(self) -> int:
        return sum(c.status == "PASS" for c in self.cases)

    @property
    def total(self) -> int:
        return len(self.cases)


@dataclasses.dataclass
class SuiteResult:
    files: list[FileResult]

    @property
    def passed(self) -> int:
        return sum(f.passed for f in self.files)

    @property
    def total(self) -> int:
        return sum(f.total for f in self.files)

    @property
    def failures(self) -> list[tuple[str, Case]]:
        return [(f.filename, c) for f in self.files for c in f.cases if c.status == "FAIL"]

    @property
    def load_errors(self) -> list[tuple[str, str]]:
        return [(f.filename, f.error) for f in self.files if f.error]


# a big real-world bundle (three.js, echarts, ...) can genuinely take a
# tree-walking interpreter a long time just to *define* itself -- cap it so
# one huge library can't stall the whole sweep, and count a timeout itself
# as a real, reportable finding rather than hanging.
_RUN_TIMEOUT = 20


@contextlib.contextmanager
def _wall_clock_limit(seconds: int):
    def _on_alarm(signum, frame):
        raise TimeoutError(f"exceeded {seconds}s")
    previous = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _fetch(url: str, timeout: float = 10.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - fetching real library bundles is the point
        return resp.read().decode("utf-8", "replace")


def _global_keys(interp: Interpreter, window) -> set[str]:
    return set(interp.global_env.vars) | set(getattr(window, "_own", {}))


def _generic_export_check(new_keys: set[str]) -> Case:
    """No hand-written assertions for this one -- did the library actually
    expose *something* real to the global scope? A UMD/IIFE bundle that
    loads without exporting anything usable is as much a real finding as
    one that throws outright."""
    useful = sorted(k for k in new_keys if not k.startswith("_") and k not in ("module", "exports", "define"))
    if useful:
        return Case("exposes a real global", "PASS", f"new: {', '.join(useful[:6])}"
                     + (f" (+{len(useful) - 6} more)" if len(useful) > 6 else ""))
    return Case("exposes a real global", "FAIL", "loaded, but no new top-level global appeared")


def _run_library(name: str, url: str) -> FileResult:
    try:
        library_src = _fetch(url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return FileResult(name, [], error=f"fetch failed: {exc}")

    g, console, document, window = default_globals()
    interp = Interpreter(g, global_object=window)
    try:
        with _wall_clock_limit(_RUN_TIMEOUT):
            interp.run(HARNESS_JS)
            before = _global_keys(interp, window)
            interp.run(library_src)
    except JSThrow as exc:
        return FileResult(name, [], error=str(exc))
    except TimeoutError:
        return FileResult(name, [], error=f"timed out after {_RUN_TIMEOUT}s (a huge bundle for a tree-walking interpreter)")
    except Exception as exc:  # noqa: BLE001 - any interpreter failure is a suite failure, not a crash
        return FileResult(name, [], error=f"{type(exc).__name__}: {exc}")
    after = _global_keys(interp, window)

    suite_file = SUITE_DIR / name
    if suite_file.is_file():
        try:
            with _wall_clock_limit(_RUN_TIMEOUT):
                interp.run(suite_file.read_text())
        except JSThrow as exc:
            return FileResult(name, [], error=str(exc))
        except TimeoutError:
            return FileResult(name, [], error=f"smoke test timed out after {_RUN_TIMEOUT}s")
        except Exception as exc:  # noqa: BLE001
            return FileResult(name, [], error=f"{type(exc).__name__}: {exc}")
        raw = interp.global_env.get("__results")
        cases = [Case(str(r.get("name")), str(r.get("status")), str(r.get("message", ""))) for r in raw]
        return FileResult(name, cases)

    return FileResult(name, [_generic_export_check(after - before)])


def run_suite(libraries: dict[str, str] | None = None, on_result=None) -> SuiteResult:
    """``on_result``, if given, is called with each :class:`FileResult` as
    it completes -- live progress for a sweep that can take a while with a
    hundred-plus live network fetches."""
    libs = libraries if libraries is not None else LIBRARY_URLS
    results = []
    for name, url in sorted(libs.items()):
        r = _run_library(name, url)
        results.append(r)
        if on_result is not None:
            on_result(r)
    return SuiteResult(results)


def format_markdown(result: SuiteResult) -> str:
    lines = [
        "# Real-world JS library sweep",
        "",
        "Generated by `python -m domonic_libs.realworld`. Each row fetches a real,",
        "popular library's actual published browser bundle live over the network --",
        "not vendored, not adapted for myjs -- through `domonic_libs.acorn.interpret`.",
        "A curated few get hand-written smoke assertions (real API calls); the rest",
        "just have to load and expose a real global, checked generically. A load",
        "error or a failing case is a genuine interpreter/domonic wrinkle candidate,",
        "found the same way the sloppy-mode `this`, ES5-prototype-chain, and",
        "`Object.prototype.toString` bugs were: run something real, see what breaks.",
        "",
        f"**Total: {result.passed} / {result.total} smoke-test assertions pass "
        f"({sum(1 for f in result.files if not f.error)} / {len(result.files)} libraries loaded).**",
        "",
        "| Library | Loaded | Pass | Total | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in result.files:
        loaded = "no" if f.error else "yes"
        note = f.error if f.error else ("all pass" if f.passed == f.total else f"{f.total - f.passed} failing")
        lines.append(f"| `{f.filename}` | {loaded} | {f.passed} | {f.total} | {note} |")
    fails = result.failures
    if fails:
        lines += ["", "## Failing assertions", ""]
        for filename, case in fails:
            lines.append(f"- **{filename}** — {case.name}: {case.message}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    import sys
    import time

    total = len(LIBRARY_URLS)

    def _progress(r, _i=[0]):
        _i[0] += 1
        status = "load-fail" if r.error else ("pass" if r.passed == r.total else f"{r.passed}/{r.total}")
        print(f"  [{_i[0]:>3}/{total}] {r.filename:<24} {status}", file=sys.stderr, flush=True)

    t0 = time.time()
    result = run_suite(on_result=_progress)
    print(f"({time.time() - t0:.0f}s total)", file=sys.stderr)
    out = Path(__file__).resolve().parents[3] / "docs" / "real-world.md"
    if out.parent.is_dir():
        out.write_text(format_markdown(result))
        print(f"wrote {out}")
    loaded = sum(1 for f in result.files if not f.error)
    print(f"{loaded}/{len(result.files)} libraries loaded, {result.passed}/{result.total} smoke assertions pass")
    for filename, error in result.load_errors:
        print(f"  LOAD FAIL {filename}: {error}")
    for filename, case in result.failures:
        print(f"  FAIL {filename}: {case.name} -- {case.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

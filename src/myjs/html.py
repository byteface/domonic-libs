"""Headless-browser mode: parse an HTML document, run its ``<script>`` elements
against that DOM, and read the result back.

    from myjs import Page

    page = Page.load("index.html")             # a local file...
    page = Page.load("https://example.com/")   # ...or a live URL

    page.query("h1").textContent            # inspect the rendered DOM
    page.eval("getComputedStyle(document.body).color")   # the CSS applied
    page.serialize()                        # the HTML after the scripts ran
    page.session.eval("someGlobal")         # poke at the page's JS state

``Page.load`` takes a local path or an ``http(s)://`` URL. When it's a URL the
page is fetched, every ``<link rel="stylesheet">`` is fetched and folded into
the document (so ``getComputedStyle`` sees the real rules), and every
``<script src>`` is fetched -- all resolved relative to the page URL. Scripts
run in document order in one shared global scope, with the real domonic DOM as
``document`` / ``window``; ``<script type="module">`` runs with module
semantics; non-JS ``type``s are skipped. ``DOMContentLoaded`` and ``load`` fire
after the scripts, and the event loop is drained. Pass ``css=False`` to skip
stylesheet fetching.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
from pathlib import Path

from ._engine import JSError, PrintConsole, Session

_UA = "myjs/headless (+https://github.com/byteface/domonic-libs)"


def _is_url(s) -> bool:
    return isinstance(s, str) and s.split(":", 1)[0].lower() in ("http", "https")


def _fetch_text(url: str, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

_JS_TYPES = {"", "text/javascript", "application/javascript", "module",
             "text/ecmascript", "application/ecmascript"}


def _parse(source: str):
    from domonic.dom import DOMParser
    return DOMParser().parseFromString(source, "text/html")


class _Location:
    """``window.location`` for a headless page -- the page's own URL."""

    def __init__(self, url="about:blank"):
        import urllib.parse
        self.href = url
        u = urllib.parse.urlparse(url)
        self.protocol = (u.scheme + ":") if u.scheme else ""
        self.host = u.netloc
        self.hostname = u.hostname or ""
        self.port = str(u.port) if u.port else ""
        self.pathname = u.path or "/"
        self.search = ("?" + u.query) if u.query else ""
        self.hash = ("#" + u.fragment) if u.fragment else ""
        self.origin = f"{u.scheme}://{u.netloc}" if u.scheme else "null"

    def toString(self):
        return self.href

    def __str__(self):
        return self.href

    def assign(self, url):
        self.href = url

    def replace(self, url):
        self.href = url

    def reload(self):
        pass


class Page:
    """A parsed HTML document whose scripts have been executed."""

    def __init__(self, source, *, base_dir=None, url="about:blank",
                 run=True, strip_scripts=False, echo=False, scope=None,
                 css=True):
        self.url = url
        # when the page came from a URL, `base_url` (not a filesystem dir) is
        # what relative `<script src>` / `<link href>` resolve against.
        self.base_url = url if _is_url(url) else None
        self.base_dir = Path(base_dir).resolve() if base_dir and not self.base_url else Path.cwd()
        self._strip = strip_scripts
        self._css = css
        self.document = _parse(source if isinstance(source, str) else source.read_text())
        console = PrintConsole() if echo else None
        page_scope = {"location": _Location(url)}
        if scope:
            page_scope.update(scope)
        self.session = Session(scope=page_scope, console=console, document=self.document)
        self.session.interp.module_base = str(self.base_dir)
        self.session.interp._cur_module["dir"] = str(self.base_dir)
        self.errors: list[JSError] = []
        if css:
            self._apply_stylesheets()
        if run:
            self.run_scripts()

    @classmethod
    def load(cls, path, **kw):
        """Load a local file *or* an ``http(s)://`` URL -- fetches the page,
        its ``<link rel=stylesheet>`` CSS, and every ``<script src>``, then
        runs the scripts against a real DOM."""
        if _is_url(path):
            kw.setdefault("url", path)
            return cls(_fetch_text(path), **kw)
        p = Path(path)
        kw.setdefault("base_dir", p.parent)
        kw.setdefault("url", p.resolve().as_uri())
        return cls(p.read_text(encoding="utf-8"), **kw)

    # -- resource resolution ---------------------------------------------

    def _resolve(self, href: str) -> str:
        """A resource URL/path referenced by the page, made absolute."""
        if href.startswith("//"):
            scheme = (self.base_url or "https:").split(":", 1)[0]
            return f"{scheme}:{href}"
        if _is_url(href):
            return href
        if self.base_url:
            return urllib.parse.urljoin(self.base_url, href)
        return str(self.base_dir / href)

    def _read_resource(self, href: str) -> str:
        target = self._resolve(href)
        if _is_url(target):
            return _fetch_text(target)
        return Path(target).read_text(encoding="utf-8")

    # -- CSS -----------------------------------------------------------

    def _apply_stylesheets(self):
        """Fetch each ``<link rel=stylesheet>`` and fold its rules into the
        document as a ``<style>`` element -- domonic's parser registers that
        in ``document.styleSheets``, so ``getComputedStyle`` sees it. Inline
        ``<style>`` already works without this."""
        for link in list(self.document.getElementsByTagName("link")):
            rel = (link.getAttribute("rel") or "").strip().lower()
            href = link.getAttribute("href")
            if "stylesheet" not in rel.split() or not href:
                continue
            try:
                css = self._read_resource(href)
            except Exception as exc:  # noqa: BLE001 -- a bad sheet must not abort the page
                self.errors.append(JSError(f"failed to load stylesheet {href!r}: {exc}",
                                           name="NetworkError"))
                continue
            try:
                style_el = self.document.createElement("style")
                style_el.textContent = css
                head = (self.document.getElementsByTagName("head") or [None])[0]
                (head or self.document.documentElement or self.document).appendChild(style_el)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(JSError(f"failed to apply stylesheet {href!r}: {exc}",
                                           name="Error"))

    # -- execution ----------------------------------------------------------

    def _script_source(self, el):
        src = el.getAttribute("src")
        if not src:
            return el.textContent or ""
        return self._read_resource(src)

    def run_scripts(self):
        scripts = list(self.document.getElementsByTagName("script"))
        for el in scripts:
            stype = (el.getAttribute("type") or "").strip().lower()
            if stype not in _JS_TYPES:
                continue
            try:
                code = self._script_source(el)
            except Exception as exc:  # noqa: BLE001 - a bad src should not abort the page
                self.errors.append(JSError(f"failed to load script: {exc}", name="NetworkError"))
                continue
            try:
                self.session.interp.run(code, module=(stype == "module") or None)
            except (Exception,) as exc:  # noqa: BLE001
                self.errors.append(_as_js_error(exc))
            if self._strip:
                _remove(el)
        self.session.interp.loop.run()
        self._fire_lifecycle()

    def _fire_lifecycle(self):
        try:
            from domonic.dom import Event
            self.document.dispatchEvent(Event("DOMContentLoaded"))
            win = self.session.window
            if hasattr(win, "dispatchEvent"):
                win.dispatchEvent(Event("load"))
        except Exception:
            pass
        self.session.interp.loop.run()

    # -- interaction (a headless automation surface) ----------------------

    def _drain(self):
        self.session.interp.loop.run()

    def _fire(self, el, *events):
        """Dispatch DOM events on a specific element from Python."""
        holder = "__myjs_el"
        self.session.interp.global_env.declare(holder, el)
        for ev in events:
            self.session.eval(f"{holder}.dispatchEvent(new Event({ev!r}, {{bubbles: true}}))")
        self._drain()

    def _el(self, target):
        """A CSS selector string, or an element passed straight through."""
        if isinstance(target, str):
            el = self.document.querySelector(target)
            if el is None:
                raise LookupError(f"no element matches {target!r}")
            return el
        return target

    def click(self, target):
        """Click a selector or element -- fires ``click`` (via ``element.click()``)."""
        holder = "__myjs_el"
        self.session.interp.global_env.declare(holder, self._el(target))
        self.session.eval(f"{holder}.click ? {holder}.click() : "
                          f"{holder}.dispatchEvent(new Event('click', {{bubbles: true}}))")
        self._drain()
        return self

    def click_all(self, selector):
        for el in list(self.document.querySelectorAll(selector)):
            self.click(el)
        return self

    def fill(self, selector, value):
        """Set an input's value and fire ``input`` + ``change``."""
        el = self._el(selector)
        el.value = str(value)
        try:
            el.setAttribute("value", str(value))
        except Exception:
            pass
        self._fire(el, "input", "change")
        return self

    def check(self, selector, checked=True):
        el = self._el(selector)
        try:
            el.checked = bool(checked)
            el.setAttribute("checked", "") if checked else el.removeAttribute("checked")
        except Exception:
            pass
        self._fire(el, "input", "change")
        return self

    def select_option(self, selector, value):
        el = self._el(selector)
        el.value = str(value)
        self._fire(el, "input", "change")
        return self

    def submit(self, selector="form"):
        el = self._el(selector)
        self._fire(el, "submit")
        return self

    def wait_for(self, selector, timeout=5.0, poll=0.02):
        """Pump the event loop until ``selector`` matches, or raise on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            self.session.interp.loop.run()
            if self.document.querySelector(selector) is not None:
                return self
            if time.monotonic() > deadline:
                raise TimeoutError(f"waited {timeout}s for {selector!r}")
            time.sleep(poll)

    def wait(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.session.interp.loop.run()
            time.sleep(min(0.02, max(0.0, end - time.monotonic())))
        return self

    # -- inspection -------------------------------------------------------

    def query(self, selector):
        return self.document.querySelector(selector)

    def query_all(self, selector):
        return list(self.document.querySelectorAll(selector))

    def get_by_id(self, id_):
        return self.document.getElementById(id_)

    def exists(self, selector):
        return self.document.querySelector(selector) is not None

    def count(self, selector):
        return len(list(self.document.querySelectorAll(selector)))

    def text(self, selector):
        el = self.document.querySelector(selector)
        return "" if el is None else (el.textContent or "")

    def attr(self, selector, name):
        el = self.document.querySelector(selector)
        return None if el is None else el.getAttribute(name)

    def value(self, selector):
        el = self.document.querySelector(selector)
        return None if el is None else (el.getAttribute("value") or getattr(el, "value", "") or "")

    def inner_html(self, selector):
        el = self.document.querySelector(selector)
        return "" if el is None else str(getattr(el, "innerHTML", "") or "")

    @property
    def title(self):
        return getattr(self.document, "title", "") or ""

    @property
    def console_lines(self):
        return self.session.console_lines

    def eval(self, src):
        return self.session.eval(src)

    # -- output ----------------------------------------------------------

    def serialize(self, *, doctype=True):
        root = str(self.document.documentElement if hasattr(self.document, "documentElement")
                   else self.document)
        return ("<!doctype html>\n" + root) if doctype else root

    def __str__(self):
        return self.serialize()


def _remove(el):
    parent = getattr(el, "parentNode", None) or getattr(el, "parentElement", None)
    try:
        if parent is not None:
            parent.removeChild(el)
    except Exception:
        pass


def _as_js_error(exc):
    if isinstance(exc, JSError):
        return exc
    val = getattr(exc, "value", None)
    if val is not None and hasattr(val, "name"):
        return JSError(str(getattr(val, "message", "") or val), name=str(val.name),
                       line=getattr(exc, "js_line", None), trace=getattr(exc, "js_trace", None))
    return JSError(str(exc), name=type(exc).__name__,
                   line=getattr(exc, "js_line", None), trace=getattr(exc, "js_trace", None))


def render(source_or_path, *, strip_scripts=False, **kw) -> str:
    """Render an HTML string or file and return the HTML after its scripts ran."""
    s = str(source_or_path)
    if "\n" not in s and "<" not in s and Path(s).is_file():
        return Page.load(s, strip_scripts=strip_scripts, **kw).serialize()
    return Page(s, strip_scripts=strip_scripts, **kw).serialize()

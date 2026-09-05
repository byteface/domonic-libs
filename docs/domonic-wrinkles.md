# domonic wrinkles

Running the ports and examples in this repo is partly a way to stress-test [domonic](https://github.com/byteface/domonic). This file collects the DOM behaviours that bit us, small and reproducible, so they can be reported and fixed in future domonic releases. Each entry has a minimal repro, what happens, and what a browser / the DOM spec does instead.

Most of the original list was fixed in **domonic 1.5.0**, **1.6.x**, and **1.7.0** -- see the Resolved sections at the bottom. Verified against **published `domonic 1.7.0`**. The curated CSSOM / DOM conformance suite (`python -m domonic_libs.conformance`, scorecard in `docs/conformance.md`) is at **50/50**. What remains:

## 1. `parseString(parser="auto")` silently cascades through absent parsers

`domonic.parseString` supports `html5lib`, `html.parser`, `lxml_html`, `html5_parser`, `markupever`, `selectolax`, `turbohtml`, `justhtml`, and `expat`. With `parser="auto"` (the default) it tries them in order and swallows `ImportError`, so on a machine where only `html5lib` is installed you are always on `html5lib` without any signal. Not a bug, but worth knowing when a parser choice is suspected: install the alternative and pass `parser=` explicitly to compare, or call `domonic.get_active_parser()` afterwards. In this repo only `html5lib` (plus stdlib `html.parser` / `expat`) is available by default.

## 2. HTML comments inside MathML survive serialisation

Wikipedia MathML contains `<mo>&#x2211;<!-- &#x2211; --></mo>` style comments. domonic keeps the `<!-- ... -->` nodes through parse -> serialise. This is spec-correct (the DOM keeps comment nodes; `innerHTML` round-trips them), but it bloats the markup; a reader that passes MathML through may want to drop comment nodes itself.

## 4. Programmatic nodes store text children as `str`

`domonic.parseString` gives real Text nodes (`nodeType == 3`, with `.data`); building the same tree with `domonic.html.p("hi", ...)` stores `"hi"` as a bare `str` in `childNodes`.

```python
from domonic.html import p, b
node = p("hi", b("x"))
type(node.childNodes[0])        # <class 'str'>   (expected: Text)
```

Code that walks a DOM generically (`node.nodeType`, `node.data`) then breaks on constructed trees. The turndown port serialises a node input back to HTML and re-parses rather than special-casing `str`.

## 6. `Element.name` is the tag name and is writable

Every domonic element exposes a `.name` property aliased to its tag / node name, and it is writable -- assigning it renames the element:

```python
from domonic.dom import document
el = document.createElementNS("http://www.w3.org/1999/xhtml", "input")
el.name                       # 'input'
el.name = "q"
str(el)                       # '<q></q>'   (expected: '<input name="q">')
```

Per the DOM there is no generic `Element.name`; on form-associated elements (`HTMLInputElement`, `HTMLFormElement`, ...) `.name` reflects the `name` content attribute. Any code that sets `element.name` as an IDL property to give a form control its submit name instead corrupts the tree. The Preact port works around this by forcing `name` through `setAttribute` (`_ATTR_ONLY` in `src/domonic_libs/preact/diff/props.py`); `getAttribute("name")` / `setAttribute("name", ...)` themselves behave correctly.

## 7. `str(node)` diverges from a browser's `innerHTML`

`node.innerHTML` / `node.outerHTML` / `node.getHTML()` now emit browser-spec HTML-fragment serialisation (`<img>` with no `/`, `checked=""`, `<` / `>` left alone in attribute values). `str(node)` / `repr` still use the older style:

```python
from domonic.html import br, input as inp, div
str(br())                                   # '<br/>'         (innerHTML: '<br>')
str(inp(_type="checkbox", _checked=""))      # '...checked/>'  (innerHTML: 'checked=""')
str(div(_title="a<b>c"))                     # 'title="a&lt;b&gt;c"'
                                            # (innerHTML: 'title="a<b>c"')
```

A port that must match browser output byte-for-byte (like DOMPurify's fixtures) should serialise through `outerHTML`, not `str(node)`.

## 8. `CanvasRenderingContext2D` / `ImageData` are recorders, and `ImageData.data` is a strict `bytearray`

`domonic.webapi.canvas.CanvasRenderingContext2D` doesn't rasterise -- it appends each call to `ctx.commands` for inspection (which is what makes it useful for headless testing: [examples/pyjs_canvas.py](../examples/pyjs_canvas.py) drives an animation and reads the draw calls back). Two consequences for a faithful port:

* `ctx.getImageData(...)` returns a **fresh zero-filled** `ImageData`, not the pixels of anything previously drawn -- there is no backing buffer to read from.
* `ImageData.data` is a plain `bytearray`, where the browser's is a `Uint8ClampedArray`. A `Uint8ClampedArray` coerces and clamps on assignment (`d[i] = 3.7` stores `4`, `d[i] = 300` stores `255`); a `bytearray` raises `TypeError` on a non-integer and `ValueError` outside `0..255`. Through the interpreter this bites quietly: `d[i] = (x * 7) % 256` no-ops, because the interpreter's `%` (like all its arithmetic -- JS has one number type) yields a Python `float`, and `bytearray.__setitem__` rejects `float` -- the exception is swallowed and the pixel stays `0`. Wrap pixel writes in `int(...)` (`d[i] = int((x * 7) % 256)`), which is idiomatic for byte values anyway. The clean upstream fix is for `ImageData.data` to be a clamping typed-array view.

---

## Resolved in domonic 1.7.0

* **Shorthand serialisation and `0` normalisation** (was #8) -- four equal longhands now collapse back into the shorthand (`s.marginTop = s.marginRight = s.marginBottom = s.marginLeft = "1px"` then `s.margin` -> `"1px"`), and a bare `"0"` length normalises to a unit (`s.padding = "0"` then `s.paddingTop` -> `"0px"`). `cssom-shorthand.js` now passes 4/4.
* **`Element.tagName` / `nodeName` are uppercase for HTML-parsed elements** (was #5), matching the spec (`document.createElement('p').tagName === 'P'` in a real browser). Anything that serialises a node to a string (rather than reading `.tagName`) must keep using the element's original lowercase local name for the printed tag -- this repo's own `dompurify.py` port was doing the former (using `.tagName` to build output tags) and needed a matching fix once 1.7 made `.tagName` correct; see `_serialize_node` in `src/domonic_libs/dompurify.py`.
* **`html.parser` inserts implied table section tags** (was #3) -- `domonic.parseString("<table><tr><td>x</td></tr></table>", parser="html.parser")` now produces `<table><tbody><tr><td>x</td></tr></tbody></table>`, matching html5lib. `tests/test_turndown.py::KNOWN_GAPS` no longer lists a table-related skip (162 passed, 4 skipped, none of them tables) -- the workaround this wrinkle used to require is gone.
* **DOMString IDL properties coerce a non-string assignment via `ToString`** (was #13) -- `span.textContent = 42; span.textContent` now correctly returns `"42"` instead of the property descriptor itself; the same fix covers `innerHTML` / `value` / `className` / `id` / `title` / etc. The interpreter's headless mode (`myjs.Page`) still `String()`-coerces a known set of stringy DOM attributes itself in `js_set` as a defensive belt-and-braces measure -- now redundant for domonic-backed elements, but harmless to keep (it also covers any non-domonic DOM stand-in).
* **`<script>` / `<style>` content serialises as raw text again** (was #14) -- `str(doc.body)` for a `<script>` containing `if (a && b) x("y");` now round-trips verbatim instead of HTML-entity-escaping it, matching the "raw text element" rule real browsers use. `myjs.Page --strip-scripts` is no longer the only safe way to serialise a document with inline scripts intact.
* **`getComputedStyle(el).camelCaseProp` no longer crashes** (`2459fa0`) -- `ComputedStyleDeclaration` deliberately skips `Style.__init__`'s hundreds of `self.__<prop> = ...` assignments (it serves every read through the cascade), but the per-property dot-access getters it inherits (`def color(self): return self.__color`) still tried to read that never-set private attribute, so `getComputedStyle(el).color` (and `.position`, `.display`, ... -- *every* property, from a stylesheet *or* an inline `style=""`) raised `AttributeError`. Nothing in the test battery exercised the dot surface -- `getComputedStyle` isn't used in the conformance suite at all, and the domonic style tests only ever went through `.getPropertyValue(...)`. Fixed in `style_get_decorator`: a missing private attribute falls back to `getPropertyValue`. This is what made `myjs.Page.load(url)` able to genuinely apply a fetched `<link rel=stylesheet>` and have `getComputedStyle` reflect it.
* **Selector-engine pseudo-classes** (`396782c`) -- `querySelector` / `querySelectorAll` now match `An+B` (`:nth-child(2n+1)`), `:nth-of-type`, `:is` / `:where` / `:has`, and form-state pseudo-classes. **Not yet wired into the `getComputedStyle` cascade**, though -- a `li:nth-child(odd) { ... }` or `a:link { ... }` rule still won't reach a matching element's *computed* style (only its selector matching). A `myjs.Page.load(url)` of a real site sees most CSS apply but misses pseudo-class-gated rules for now.
* **Nodes built inside a `with` block aren't double-appended** (`bc78e80`).
* **Big performance work landed** -- `~48x faster CSSStyleDeclaration()` (lazy property defaults), `~38% faster import domonic` (deferred `elementpath` / `multiprocessing` imports), cached `RegExp._compiled()`, `String`/`Number` with `__slots__` + coercion dedupe, and `_insert` no longer materialising the child list. Nothing in this repo's suites regressed against published 1.7.0.

The conformance suite (`python -m domonic_libs.conformance`) is now 50/50 -- `cssom-shorthand.js` and `cssom-style-declaration.js` both pass in full.

---

## Resolved in domonic 1.6.x

Wrinkles #9-#12 (from the CSSOM/DOM conformance suite) were fixed:

* **`cssText` set via the setter re-serialises** with the trailing `;` / single-space form, matching the `setProperty` path.
* **The `style` IDL attribute is backed by the `style` content attribute** -- `setAttribute("style", "")` / `removeAttribute("style")` clears the declaration.
* **`Element.getAttributeNames()` is implemented.**
* **Attribute names are ASCII-lower-cased on HTML elements** -- `setAttribute("FOO", "1")` then `getAttribute("foo")` returns `"1"`.

The conformance suite (`python -m domonic_libs.conformance`) now sits at 46/49.

---

## Resolved in domonic 1.5.0

The port work below surfaced these; each was then fixed upstream.

* **Attribute values are now escaped on serialisation.** `&` -> `&amp;` and `"` -> `&quot;` in `str()` / `outerHTML` / `innerHTML`, so markup round-trips.
* **The html5lib tree builder keeps whitespace-only text nodes.** `<b>x</b> <i>y</i>` now parses with the space intact, so turndown's flanking-whitespace logic and DOMPurify no longer need workarounds.
* **`html.parser` implied tags** -- `<p>` / `<li>` auto-close and `<ul>`/`<ol>` nesting inside `<li>` now match html5lib (table sections were still pending here; fixed in 1.7.0, see above).
* **`domonic.javascript` string/regex is a viable target for a regex-heavy port.** `String.replace` expands `$1`..`$n` and `$<name>`; `RegExp` has a `replace` method, the sticky (`y`) flag and `lastIndex`; and `\p{P}` / `\p{S}` / `\p{L}` Unicode property classes compile.
* **Elements expose `on<event>` for feature detection.** `'onclick' in button_element` is `True`.
* **Clearing a CSS property with `""` drops the declaration.** `el.style["color"] = ""` now serialises `style=""`, not `style="color: ;"`.
* **SVG text measurement and geometry.** `Element.getBBox()` measures `<text>` / `<tspan>` with bundled font metrics, unions `<g>` children with their `transform` applied, and `getComputedTextLength()` / `getSubStringLength()` / `getScreenCTM()` are implemented and transform-aware. Elements from `createElementNS` and `d3.selection.append()` carry the same SVG API as the `domonic.svg.*` factories. This unblocked the Mermaid renderers.
* **`d3.shape.arc()` reads its angles from the datum.** A bare `arc().innerRadius(0).outerRadius(r)` fed `d3.pie()` output now draws wedges, not full circles. (d3 accessor callbacks are still invoked `(d, i, data)`, so Python code must use `lambda d, *_: ...`.)

---

## Readability port notes (not domonic bugs)

`src/domonic_libs/readability.py` is a faithful port of Mozilla's Readability.js, including `_isProbablyVisible`, which removes any node with `display: none`, `visibility: hidden`, `hidden`, or `aria-hidden="true"`. Wikipedia ships each formula as MathML hidden behind `display: none` plus an `aria-hidden` raster fallback, so **stock Readability discards all of the math** (Firefox Reader View has the same limitation). `content/content.py` works around this by rewriting the math islands *before* handing the document to Readability: display formulas become a visible `div.math-block` carrying the MathML, inline formulas become TeX in `\(...\)` delimiters for MathJax.


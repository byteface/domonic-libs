# domonic wrinkles

Running the ports and examples in this repo is partly a way to stress-test [domonic](https://github.com/byteface/domonic). This file collects the DOM behaviours that bit us, small and reproducible, so they can be reported and fixed in future domonic releases. Each entry has a minimal repro, what happens, and what a browser / the DOM spec does instead.

Most of the original list was fixed in **domonic 1.5.0** and **1.6.x** -- see the Resolved sections at the bottom. The curated CSSOM / DOM conformance suite (`python -m domonic_libs.conformance`, scorecard in `docs/conformance.md`) is at 46/49. What remains:

## 1. `parseString(parser="auto")` silently cascades through absent parsers

`domonic.parseString` supports `html5lib`, `html.parser`, `lxml_html`, `html5_parser`, `markupever`, `selectolax`, `turbohtml`, `justhtml`, and `expat`. With `parser="auto"` (the default) it tries them in order and swallows `ImportError`, so on a machine where only `html5lib` is installed you are always on `html5lib` without any signal. Not a bug, but worth knowing when a parser choice is suspected: install the alternative and pass `parser=` explicitly to compare, or call `domonic.get_active_parser()` afterwards. In this repo only `html5lib` (plus stdlib `html.parser` / `expat`) is available by default.

## 2. HTML comments inside MathML survive serialisation

Wikipedia MathML contains `<mo>&#x2211;<!-- &#x2211; --></mo>` style comments. domonic keeps the `<!-- ... -->` nodes through parse -> serialise. This is spec-correct (the DOM keeps comment nodes; `innerHTML` round-trips them), but it bloats the markup; a reader that passes MathML through may want to drop comment nodes itself.

## 3. `html.parser` does not insert table section tags

`parser="html.parser"` now handles most implied-tag cases -- it auto-closes `<p>` and `<li>`, and nests `<ul>`/`<ol>` inside an `<li>` correctly (this used to be broken). The remaining gap is table sections: it does **not** insert `<tbody>` / `<thead>` the way the HTML5 tree builder does.

```python
from domonic import domonic
domonic.parseString("<table><tr><td>x</td></tr></table>", parser="html.parser")
# <table><tr><td>x</td></tr></table>          (html5lib: ...<tbody><tr>...)
```

The turndown port uses `parser="html.parser"` (to keep significant whitespace) and skips a couple of table fixtures for this reason (`tests/test_turndown.py::KNOWN_GAPS`).

## 4. Programmatic nodes store text children as `str`

`domonic.parseString` gives real Text nodes (`nodeType == 3`, with `.data`); building the same tree with `domonic.html.p("hi", ...)` stores `"hi"` as a bare `str` in `childNodes`.

```python
from domonic.html import p, b
node = p("hi", b("x"))
type(node.childNodes[0])        # <class 'str'>   (expected: Text)
```

Code that walks a DOM generically (`node.nodeType`, `node.data`) then breaks on constructed trees. The turndown port serialises a node input back to HTML and re-parses rather than special-casing `str`.

## 5. `Element.nodeName` / `tagName` are lower-case

```python
from domonic import domonic
el = domonic.parseString("<div></div>").getElementsByTagName("div")[0]
el.nodeName        # 'div'   (spec: 'DIV' for an HTML element in an HTML document)
el.tagName         # 'div'
```

`localName` should stay lower-case; `nodeName` and `tagName` should be upper-cased for HTML elements. turndown.js and DOMPurify both compare against upper-case tag literals throughout, so the ports normalise the case themselves.

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

## 8. A CSS shorthand does not contribute its longhands to `style.length`

The only survivor of the CSSOM batch. Setting `margin` now correctly populates `marginTop` etc. (fixed since this was logged), but the shorthand still counts as a single entry:

```python
from domonic.html import div
s = div().style
s.margin = "1px 2px 3px 4px"
s.marginTop            # '1px'   -- correct now
s.length               # 1       (browser: 4 -- stored as the four longhands)
```

Per CSSOM a shorthand is stored *as* its longhand declarations, so `length` should be 4 and `s.margin` should re-serialise from four equal longhands. `src/domonic_libs/conformance/suite/cssom-shorthand.js` covers it; 3 of its 4 assertions still fail here.

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
* **`html.parser` implied tags** -- `<p>` / `<li>` auto-close and `<ul>`/`<ol>` nesting inside `<li>` now match html5lib (table sections still pending, #3).
* **`domonic.javascript` string/regex is a viable target for a regex-heavy port.** `String.replace` expands `$1`..`$n` and `$<name>`; `RegExp` has a `replace` method, the sticky (`y`) flag and `lastIndex`; and `\p{P}` / `\p{S}` / `\p{L}` Unicode property classes compile.
* **Elements expose `on<event>` for feature detection.** `'onclick' in button_element` is `True`.
* **Clearing a CSS property with `""` drops the declaration.** `el.style["color"] = ""` now serialises `style=""`, not `style="color: ;"`.
* **SVG text measurement and geometry.** `Element.getBBox()` measures `<text>` / `<tspan>` with bundled font metrics, unions `<g>` children with their `transform` applied, and `getComputedTextLength()` / `getSubStringLength()` / `getScreenCTM()` are implemented and transform-aware. Elements from `createElementNS` and `d3.selection.append()` carry the same SVG API as the `domonic.svg.*` factories. This unblocked the Mermaid renderers.
* **`d3.shape.arc()` reads its angles from the datum.** A bare `arc().innerRadius(0).outerRadius(r)` fed `d3.pie()` output now draws wedges, not full circles. (d3 accessor callbacks are still invoked `(d, i, data)`, so Python code must use `lambda d, *_: ...`.)

---

## Readability port notes (not domonic bugs)

`src/domonic_libs/readability.py` is a faithful port of Mozilla's Readability.js, including `_isProbablyVisible`, which removes any node with `display: none`, `visibility: hidden`, `hidden`, or `aria-hidden="true"`. Wikipedia ships each formula as MathML hidden behind `display: none` plus an `aria-hidden` raster fallback, so **stock Readability discards all of the math** (Firefox Reader View has the same limitation). `content/content.py` works around this by rewriting the math islands *before* handing the document to Readability: display formulas become a visible `div.math-block` carrying the MathML, inline formulas become TeX in `\(...\)` delimiters for MathJax.


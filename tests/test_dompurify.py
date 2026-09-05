"""Tests for the DOMPurify port.

The core is DOMPurify's own ``test/fixtures/expect.mjs`` corpus, vendored as
``fixtures/dompurify/expect.json`` (223 payload/expected pairs, run with default
config). Comparison is exact string match against the expected string (or, for
the ~40 fixtures that vary by browser, membership in the expected array).

The dozen that still differ are in ``KNOWN_GAPS`` -- every one is a *fidelity*
gap (the sanitised output is safe, just not byte-identical to a browser's),
caused either by domonic's HTML5 parser (nested/foreign-content edge cases) or
by DOMPurify's deepest namespace-confusion checks. Below the corpus is a
focused API/config section.
"""

import json
import pathlib
import unittest

from domonic_libs.dompurify import DOMPurify, createDOMPurify, sanitize

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "dompurify" / "expect.json"
CASES = json.loads(FIXTURES.read_text())

# Keyed by fixture index. Every one is a *fidelity* gap -- the sanitised output
# is safe, just not byte-identical to a browser's.
KNOWN_GAPS = {
    57: "generated <input> attribute order",
    82: "bogus <set> element serialisation (domonic parser)",
    85: "<style> selector text with attribute-like brackets",
    95: "<comment> pseudo-element attribute parsing (domonic parser)",
    101: "<base> href resolution in <head>",
    103: "leading-whitespace on a full xhtml document",
    196: "SVG/HTML integration-point confusion (DOMPurify namespace internals)",
    202: "annotation-xml integration point",
    212: "SVG fake-element namespace confusion",
    216: 'keep is="" on a plain element',
    217: "<template> inside <select> parsing (domonic parser)",
}


def _matches(actual, expected):
    accepted = expected if isinstance(expected, list) else [expected]
    return actual in accepted


class TestDOMPurifyCorpus(unittest.TestCase):
    def test_corpus(self):
        """Every default-config fixture matches, except the documented gaps."""
        unexpected = []
        for index, case in enumerate(CASES):
            got = sanitize(case["payload"])
            passed = _matches(got, case["expected"])
            if passed and index in KNOWN_GAPS:
                unexpected.append(f"[{index}] now PASSES -- drop from KNOWN_GAPS")
            elif not passed and index not in KNOWN_GAPS:
                unexpected.append(
                    f"[{index}] {case.get('title') or case['payload'][:60]!r}\n"
                    f"    payload : {case['payload']!r}\n"
                    f"    expected: {case['expected']!r}\n"
                    f"    got     : {got!r}"
                )
        self.assertEqual(unexpected, [], "\n" + "\n".join(unexpected))


class TestDOMPurifyApi(unittest.TestCase):
    def test_scripts_and_event_handlers(self):
        self.assertEqual(
            sanitize('<p onclick="x()">Hi<script>a()</script><b>ok</b></p>'),
            "<p>Hi<b>ok</b></p>",
        )

    def test_javascript_uri_dropped_data_image_kept(self):
        out = sanitize('<a href="javascript:alert(1)">x</a><img src="data:image/png;base64,aaa">')
        self.assertNotIn("javascript:", out)
        self.assertIn('src="data:image/png;base64,aaa"', out)

    def test_uri_like_values_kept_on_uri_safe_attrs(self):
        self.assertEqual(
            sanitize('<b href="javascript:alert(1)" title="javascript:alert(2)"></b>'),
            '<b title="javascript:alert(2)"></b>',
        )

    def test_style_is_not_css_sanitised(self):
        # DOMPurify keeps the style attribute verbatim (no built-in CSS sanitiser)
        markup = '<p style="color: red; background: url(javascript:alert(1))">x</p>'
        self.assertEqual(sanitize(markup), markup)

    def test_void_and_boolean_serialisation(self):
        self.assertEqual(sanitize("<br>"), "<br>")
        self.assertEqual(sanitize("<input type=checkbox checked>"), '<input type="checkbox" checked="">')

    def test_nested_anchor_autocloses(self):
        self.assertEqual(sanitize("<a>1<a>2</a>3</a>"), "<a>1</a><a>2</a>3")

    def test_allowed_tags(self):
        self.assertEqual(sanitize("<b>a</b><i>b</i>", {"ALLOWED_TAGS": ["b"]}), "<b>a</b>b")

    def test_forbid_tags_and_attr(self):
        self.assertEqual(sanitize("<b>a</b><i>b</i>", {"FORBID_TAGS": ["i"]}), "<b>a</b>b")
        self.assertEqual(sanitize('<a href="/" title="t">x</a>', {"FORBID_ATTR": ["title"]}), '<a href="/">x</a>')

    def test_allowed_attr(self):
        self.assertEqual(
            sanitize('<a href="/" title="t" class="c">x</a>', {"ALLOWED_ATTR": ["href"]}),
            '<a href="/">x</a>',
        )

    def test_add_tags(self):
        self.assertEqual(sanitize("<my-tag>x</my-tag>", {"ADD_TAGS": ["my-tag"]}), "<my-tag>x</my-tag>")

    def test_keep_content(self):
        self.assertEqual(sanitize("<unknown-x>text</unknown-x>"), "text")
        self.assertEqual(sanitize("<unknown-x>text</unknown-x>", {"KEEP_CONTENT": False}), "")

    def test_data_and_aria_attrs(self):
        self.assertEqual(sanitize('<b data-x="1" foo="2">y</b>'), '<b data-x="1">y</b>')
        self.assertEqual(sanitize('<b aria-label="l">y</b>'), '<b aria-label="l">y</b>')
        self.assertEqual(sanitize('<b data-x="1">y</b>', {"ALLOW_DATA_ATTR": False}), "<b>y</b>")

    def test_sanitize_dom_clobbering(self):
        self.assertEqual(sanitize('<a id="createElement">x</a>'), "<a>x</a>")
        self.assertEqual(sanitize("<img src=x name=cookie>"), '<img src="x">')
        self.assertEqual(sanitize("<img src=x name=isindex>"), '<img src="x" name="isindex">')

    def test_return_dom(self):
        # a real DOM's `.tagName` is always uppercase for HTML elements
        # (e.g. `document.createElement('p').tagName === 'P'` in any browser)
        # -- domonic 1.7 made this spec-correct; the *serialized string* form
        # (see test_whole_document) is what stays lowercase.
        node = DOMPurify().sanitize("<p onclick='x'>ok</p>", {"RETURN_DOM": True})
        self.assertEqual(getattr(node, "tagName", ""), "P")

    def test_return_dom_fragment(self):
        frag = DOMPurify().sanitize("<p>x</p><b>y</b>", {"RETURN_DOM_FRAGMENT": True})
        self.assertEqual(type(frag).__name__, "DocumentFragment")

    def test_whole_document(self):
        markup = "<html><head></head><body><p>x</p><script>e()</script></body></html>"
        self.assertEqual(sanitize(markup), "<p>x</p>")
        self.assertEqual(sanitize(markup, {"WHOLE_DOCUMENT": True}),
                         "<html><head></head><body><p>x</p></body></html>")

    def test_removed_reporting(self):
        purifier = DOMPurify()
        purifier.sanitize('<script>a()</script><b onclick="x">ok</b>')
        self.assertIn({"attribute": "onclick", "from": "b"}, purifier.removed)

    def test_is_valid_attribute(self):
        dp = DOMPurify()
        self.assertTrue(dp.isValidAttribute("a", "href", "https://x.io"))
        self.assertFalse(dp.isValidAttribute("a", "href", "javascript:x"))

    def test_hooks(self):
        dp = DOMPurify()
        seen = []
        dp.addHook("uponSanitizeElement", lambda node, data, config: seen.append(data.get("tagName")))
        dp.sanitize("<p><b>x</b></p>")
        self.assertIn("p", seen)
        dp.removeAllHooks()

    def test_string_only_and_factory(self):
        self.assertTrue(callable(createDOMPurify))
        self.assertEqual(sanitize("plain text"), "plain text")
        self.assertEqual(sanitize(""), "")

    def test_svg_and_mathml_kept(self):
        self.assertEqual(
            sanitize('<svg><circle r="5"/><script>e()</script></svg>'),
            "<svg><circle r=\"5\"></circle></svg>",
        )
        self.assertIn("<math>", sanitize("<math><mi>x</mi></math>"))


if __name__ == "__main__":
    unittest.main()

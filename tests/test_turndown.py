"""Tests for the turndown.js port.

The bulk of the coverage is turndown's own fixture suite, vendored verbatim as
``fixtures/turndown_cases.html`` from mixmark-io/turndown. A handful of cases
depend on HTML tree-construction that domonic's parsers do not implement (deep
list nesting, some ``<pre>`` whitespace); those are listed in ``KNOWN_GAPS``
with the underlying reason and skipped rather than silently xfailed.
"""

import json
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET

import html5lib

from domonic_libs.turndown import TurndownService, turndown
from domonic_libs.turndown.gfm import gfm

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "turndown_cases.html"
GFM_FIXTURE = FIXTURES / "turndown_gfm_cases.html"

# name -> reason. Each is a domonic parser limitation, not a port bug.
# (`html.parser` list nesting was fixed in domonic 1.5.0, so those cases now run.)
KNOWN_GAPS = {
    "empty line in start/end of code block": "domonic collapses <pre> edge newlines",
    "list-like text with non-breaking spaces": "text node split around an HTML comment",
}

# turndown-plugin-gfm master ships fixtures ahead of its own src/tables.js.
GFM_KNOWN_GAPS = {
    "empty rows": "upstream gfm master does not filter empty <tr>",
    "empty head": "upstream gfm master does not filter empty heading rows",
}


def _camel_to_snake(key):
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), key)


def _inner_html(element):
    parts = [element.text or ""]
    for child in element:
        parts.append(ET.tostring(child, encoding="unicode", method="html"))
    return "".join(parts).strip()


def _load_cases(path):
    document = html5lib.parse(path.read_text(), namespaceHTMLElements=False)
    cases = []
    for node in document.iter("div"):
        if node.get("class") != "case":
            continue
        name = node.get("data-name")
        options = json.loads(node.get("data-options")) if node.get("data-options") else {}
        input_el = next(c for c in node.iter("div") if c.get("class") == "input")
        expected_el = next(c for c in node.iter("pre") if c.get("class") == "expected")
        cases.append((name, options, _inner_html(input_el), expected_el.text or ""))
    return cases


class TestTurndownFixtures(unittest.TestCase):
    pass


class TestTurndownGfmFixtures(unittest.TestCase):
    pass


def _make_fixture_test(name, options, source, expected, gaps, plugin=None):
    def test(self):
        if name in gaps:
            self.skipTest(gaps[name])
        kwargs = {_camel_to_snake(k): v for k, v in options.items()}
        service = TurndownService(**kwargs)
        if plugin is not None:
            service.use(plugin)
        self.assertEqual(service.turndown(source), expected)

    test.__name__ = "test_" + re.sub(r"\W+", "_", name)
    return test


for _name, _options, _source, _expected in _load_cases(FIXTURE):
    _t = _make_fixture_test(_name, _options, _source, _expected, KNOWN_GAPS)
    setattr(TestTurndownFixtures, _t.__name__, _t)

for _name, _options, _source, _expected in _load_cases(GFM_FIXTURE):
    _t = _make_fixture_test(
        _name, _options, _source, _expected, GFM_KNOWN_GAPS, plugin=gfm
    )
    setattr(TestTurndownGfmFixtures, _t.__name__, _t)


class TestTurndownApi(unittest.TestCase):
    def test_module_helper(self):
        self.assertEqual(
            turndown("<h1>Hello</h1><p>A <strong>bold</strong> <a href='/x'>link</a>.</p>"),
            "Hello\n=====\n\nA **bold** [link](/x).",
        )

    def test_empty_string(self):
        self.assertEqual(TurndownService().turndown(""), "")

    def test_none_input_raises(self):
        with self.assertRaisesRegex(TypeError, "is not a string"):
            TurndownService().turndown(None)

    def test_add_rule_returns_instance_and_applies(self):
        service = TurndownService()
        rule = {
            "filter": ["del", "s", "strike"],
            "replacement": lambda content, node, options: "~~" + content + "~~",
        }
        self.assertIs(service.add_rule("strikethrough", rule), service)
        self.assertEqual(service.turndown("<del>redact</del>"), "~~redact~~")

    def test_use_runs_plugins_and_chains(self):
        service = TurndownService()
        seen = []
        self.assertIs(service.use([lambda s: seen.append(s), lambda s: seen.append(s)]), service)
        self.assertEqual(seen, [service, service])

    def test_keep_keeps_elements_as_html(self):
        service = TurndownService()
        markup = "<p>Hello <del>world</del><ins>World</ins></p>"
        self.assertEqual(service.turndown(markup), "Hello worldWorld")
        service.keep(["del", "ins"])
        self.assertEqual(service.turndown(markup), "Hello <del>world</del><ins>World</ins>")

    def test_keep_is_overridden_by_standard_rules(self):
        service = TurndownService()
        service.keep("p")
        self.assertEqual(service.turndown("<p>Hello world</p>"), "Hello world")

    def test_remove_removes_elements(self):
        service = TurndownService()
        self.assertEqual(service.turndown("<del>redact me</del>"), "redact me")
        service.remove("del")
        self.assertEqual(service.turndown("<del>redact me</del>"), "")

    def test_reference_links(self):
        service = TurndownService(link_style="referenced")
        self.assertEqual(
            service.turndown('<a href="http://example.com">example</a>'),
            "[example][1]\n\n[1]: http://example.com",
        )

    def test_accepts_a_domonic_node(self):
        from domonic.html import p, strong

        node = p("Hello ", strong("bold"))
        self.assertEqual(TurndownService().turndown(node), "Hello **bold**")


class TestTurndownInternals(unittest.TestCase):
    def test_edge_whitespace_detection(self):
        from domonic_libs.turndown.node import _edge_whitespace

        ws = "\r\n \t"

        def ews(leading_ascii, leading_non_ascii, trailing_non_ascii, trailing_ascii):
            return {
                "leading": leading_ascii + leading_non_ascii,
                "leadingAscii": leading_ascii,
                "leadingNonAscii": leading_non_ascii,
                "trailing": trailing_non_ascii + trailing_ascii,
                "trailingNonAscii": trailing_non_ascii,
                "trailingAscii": trailing_ascii,
            }

        cases = [
            (f"{ws}HELLO WORLD{ws}", ews(ws, "", "", ws)),
            (f"{ws}H{ws}", ews(ws, "", "", ws)),
            (f"{ws}\xa0{ws}HELLO{ws}WORLD{ws}\xa0{ws}", ews(ws, f"\xa0{ws}", f"{ws}\xa0", ws)),
            (f"\xa0{ws}HELLO{ws}WORLD{ws}\xa0", ews("", f"\xa0{ws}", f"{ws}\xa0", "")),
            (f"\xa0{ws}\xa0", ews("", f"\xa0{ws}\xa0", "", "")),
            (f"{ws}\xa0{ws}", ews(ws, f"\xa0{ws}", "", "")),
            (f"{ws}\xa0", ews(ws, "\xa0", "", "")),
            ("HELLO WORLD", ews("", "", "", "")),
            ("", ews("", "", "", "")),
            ("TEST" + " " * 32767 + "END", ews("", "", "", "")),
        ]
        for value, expected in cases:
            self.assertEqual(_edge_whitespace(value), expected)


if __name__ == "__main__":
    unittest.main()

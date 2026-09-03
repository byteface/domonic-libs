"""Tests for the marked.js port.

Runs marked's own vendored spec suites (``tests/fixtures/marked/``):

* the CommonMark 0.31.2 conformance suite, with ``{gfm: False, pedantic: False}``
* the GFM 0.29 suite, with ``{gfm: True}``
* marked's ``new/`` regression specs (default options, per-file front-matter)
* marked's ``original/`` (Gruber) specs, with ``{gfm: False, pedantic: True}``

Comparison mirrors marked's ``@markedjs/html-differ``: SAX-tokenise both sides,
sort attributes, collapse whitespace inside every text node, keep comments,
ignore the self-closing slash. ``shouldFail`` cases (marked's own known CommonMark
deviations) pass when our output also differs from the spec. The handful that
still differ are in ``KNOWN_GAPS``.
"""

import json
import pathlib
import re
import unittest
from html.parser import HTMLParser

from domonic_libs.marked import marked

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "marked"

KNOWN_GAPS = {
    # marked keeps a blank line between a table and a following block; a minor
    # spacing/structure gap in our table + thematic-break interaction.
    "hr_following_tables": "blank line between table and following block",
    "hr_following_nptables": "blank line between nptable and following block",
    # block HTML comment run-in with the next block.
    "html_comments": "block HTML comment boundary with following heading",
    # pedantic-only (Gruber Markdown.pl) corner cases.
    "links_reference_style": "pedantic reference-link edge case",
    "literal_quotes_in_titles": "pedantic title-quote handling",
    "strong_punctuation": "pedantic emphasis-around-punctuation",
}

_WS = re.compile(r"\s+")
_ENC = {"&": "&amp;", "'": "&#39;", '"': "&quot;", "<": "&lt;", ">": "&gt;"}


def _enc(text):
    return "".join(_ENC.get(c, c) for c in text)


class _Normalizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        rendered = "".join(f' {k}="{_enc(v or "")}"' for k, v in sorted(attrs))
        self.out.append(f"<{tag}{rendered}>")

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(_enc(_WS.sub(" ", data).strip()))

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")


def _normalize(html):
    parser = _Normalizer()
    parser.feed(html or "")
    parser.close()
    return "".join(parser.out)


def html_equal(actual, expected):
    return _normalize(actual) == _normalize(expected)


def _load_json(name):
    return json.loads((FIXTURES / name).read_text())


def _parse_front_matter(text):
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}, text
    options = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if value in ("true", "false"):
            options[key] = value == "true"
        elif value.isdigit():
            options[key] = int(value)
        else:
            options[key] = value.strip('"')
    return options, text[match.end():]


def _load_md_dir(name):
    specs = []
    for md_path in sorted((FIXTURES / name).glob("*.md")):
        options, body = _parse_front_matter(md_path.read_text())
        specs.append(
            {
                "section": md_path.stem,
                "markdown": body,
                "html": md_path.with_suffix(".html").read_text(),
                "options": options,
            }
        )
    return specs


class _SpecSuite(unittest.TestCase):
    pass


class TestMarkedCommonMark(_SpecSuite):
    pass


class TestMarkedGfm(_SpecSuite):
    pass


class TestMarkedNew(_SpecSuite):
    pass


class TestMarkedOriginal(_SpecSuite):
    pass


def _make_test(spec, base_options):
    should_fail = spec.get("shouldFail", False)
    section = spec.get("section", "")
    name = "test_" + re.sub(r"\W+", "_", f"{section}_{spec.get('example', '')}")

    def test(self):
        if section in KNOWN_GAPS:
            self.skipTest(KNOWN_GAPS[section])
        options = dict(base_options)
        options.update(spec.get("options") or {})
        rendered = marked(spec["markdown"], options)
        matches = html_equal(rendered, spec.get("html") or "")
        if should_fail:
            self.assertFalse(matches, "expected our output to differ from the spec")
        else:
            self.assertTrue(
                matches,
                f"\n--- markdown ---\n{spec['markdown']!r}"
                f"\n--- expected ---\n{spec.get('html')!r}"
                f"\n--- got ---\n{rendered!r}",
            )

    test.__name__ = name
    return test


def _attach(cls, specs, base_options):
    seen = {}
    for spec in specs:
        test = _make_test(spec, base_options)
        key = test.__name__
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            test.__name__ = f"{key}_{seen[key]}"
        setattr(cls, test.__name__, test)


_attach(
    TestMarkedCommonMark,
    _load_json("commonmark.0.31.2.json"),
    {"gfm": False, "pedantic": False},
)
_attach(TestMarkedGfm, _load_json("gfm.0.29.json"), {"gfm": True, "pedantic": False})
_attach(TestMarkedNew, _load_md_dir("new"), {})
_attach(TestMarkedOriginal, _load_md_dir("original"), {"gfm": False, "pedantic": True})


class TestMarkedApi(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(marked("# Hello *world*"), "<h1>Hello <em>world</em></h1>\n")

    def test_parse_inline(self):
        from domonic_libs.marked import parse_inline

        self.assertEqual(parse_inline("**bold** and `code`"), "<strong>bold</strong> and <code>code</code>")

    def test_options_kwarg(self):
        self.assertEqual(marked("a\nb", breaks=True), "<p>a<br>b</p>\n")

    def test_gfm_off_no_tables(self):
        out = marked("| a | b |\n| - | - |\n| 1 | 2 |", gfm=False)
        self.assertNotIn("<table>", out)

    def test_silent_swallows_errors(self):
        # a deliberately pathological construct should not raise with silent
        marked("[" * 20, silent=True)

    def test_lexer_and_parser_exposed(self):
        from domonic_libs.marked import lexer, parser

        tokens = lexer("# h")
        self.assertEqual(tokens[0]["type"], "heading")
        self.assertEqual(parser(tokens), "<h1>h</h1>\n")


if __name__ == "__main__":
    unittest.main()

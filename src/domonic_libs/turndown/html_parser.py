# Ported from mixmark-io/turndown (MIT). Mirrors src/html-parser.js.
"""Parse an HTML string into a DOM subtree rooted at a single element.

turndown.js wraps the input in ``<x-turndown>`` so a spec HTML parser keeps
everything under one element instead of splitting it across ``<head>`` and
``<body>``. We do the same and parse with domonic.

Parser choice is a compromise, and both options are domonic wrinkles worth
feeding back (see ``docs/domonic-wrinkles.md``):

* ``html5lib`` does proper HTML5 tree construction, but domonic's tree builder
  discards every whitespace-only text node, so significant whitespace between
  inline elements (``<b>x</b> <i>y</i>``) is lost -- which turndown's flanking
  whitespace logic depends on.
* ``html.parser`` keeps that whitespace, so it is the better base here, but it
  does not implement implied tags, so deeply nested ``<ul>``/``<ol>`` inside
  ``<li>`` can be mis-nested.

``html.parser`` wins on turndown's own fixture suite (142/147 vs 124/147), so
that is what we use.
"""

from __future__ import annotations

from domonic import domonic

ROOT_ID = "turndown-root"
ROOT_TAG = "x-turndown"


def parse_html(string):
    doc = domonic.parseString(
        f'<{ROOT_TAG} id="{ROOT_ID}">{string}</{ROOT_TAG}>',
        parser="html.parser",
    )

    if (getattr(doc, "tagName", "") or "").lower() == ROOT_TAG:
        return doc

    if hasattr(doc, "getElementById"):
        try:
            root = doc.getElementById(ROOT_ID)
        except Exception:
            root = None
        if root is not None:
            return root

    for child in getattr(doc, "childNodes", []) or []:
        if (getattr(child, "tagName", "") or "").lower() == ROOT_TAG:
            return child

    found = doc.getElementsByTagName(ROOT_TAG)
    return found[0] if found else doc

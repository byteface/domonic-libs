from __future__ import annotations

import argparse
import json
import sys

from . import DomUtils, ElementType, getInnerHTML, parseDocument, textContent


def _read(path: str | None) -> str:
    if path in (None, "-"):
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write(text: str, path: str | None) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return
    print(text)


def _stats(html: str) -> dict:
    doc = parseDocument(html)
    counts: dict[str, int] = {}

    def walk(node):
        node_type = getattr(node, "type", None) or (
            ElementType.Text if getattr(node, "nodeType", None) == 3 else "node"
        )
        counts[node_type] = counts.get(node_type, 0) + 1
        for child in DomUtils.getChildren(node):
            walk(child)

    walk(doc)
    title = DomUtils.getElementsByTagName("title", doc, True, 1)
    return {
        "bytes": len(html.encode("utf-8")),
        "nodes": sum(counts.values()),
        "counts": counts,
        "title": textContent(title[0]).strip() if title else "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="htmlparser2", description="Parse HTML with the htmlparser2 port.")
    parser.add_argument("input", nargs="?", help="HTML file to read, or stdin when omitted / '-'")
    parser.add_argument("-o", "--output", help="write output to a file")
    parser.add_argument("--text", action="store_true", help="print textContent instead of HTML")
    parser.add_argument("--stats", action="store_true", help="print parser stats as JSON")
    parser.add_argument("--domonic-backend", action="store_true", help="parse through domonic.parseString(parser='htmlparser2')")
    parser.add_argument("--prefer-auto", action="store_true", help="with --domonic-backend, prefer htmlparser2 for parser='auto'")
    args = parser.parse_args(argv)

    html = _read(args.input)

    if args.stats:
        _write(json.dumps(_stats(html), indent=2, sort_keys=True), args.output)
        return 0

    if args.text:
        _write(textContent(parseDocument(html)), args.output)
        return 0

    if args.domonic_backend:
        from domonic import domonic

        from . import install_domonic_parser

        install_domonic_parser(prefer_auto=args.prefer_auto)
        page = domonic.parseString(html, parser="auto" if args.prefer_auto else "htmlparser2")
        _write(str(page), args.output)
        return 0

    _write(getInnerHTML(parseDocument(html)), args.output)
    return 0

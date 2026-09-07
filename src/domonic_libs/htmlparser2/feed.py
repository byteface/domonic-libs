# Ported-shape feed helper for htmlparser2.

from __future__ import annotations

from .domutils import getElementsByTagName, textContent


def _first_text(name, root):
    nodes = getElementsByTagName(name, root)
    return textContent(nodes[0]).strip() if nodes else ""


def getFeed(children):
    root = children
    rss = getElementsByTagName("rss", root)
    feed = getElementsByTagName("feed", root)
    if rss:
        return {
            "type": "rss",
            "title": _first_text("title", root),
            "link": _first_text("link", root),
            "description": _first_text("description", root),
            "items": [
                {"title": _first_text("title", item), "link": _first_text("link", item)}
                for item in getElementsByTagName("item", root)
            ],
        }
    if feed:
        return {
            "type": "atom",
            "title": _first_text("title", root),
            "link": _first_text("link", root),
            "description": _first_text("subtitle", root),
            "items": [
                {"title": _first_text("title", entry), "link": _first_text("link", entry)}
                for entry in getElementsByTagName("entry", root)
            ],
        }
    return None


def parseFeed(feed, options=None):
    from . import parseDocument

    opts = {"xmlMode": True}
    opts.update(options or {})
    return getFeed(parseDocument(feed, opts).args)


# Ported from markedjs/marked (MIT). Mirrors src/Renderer.ts.
"""Default HTML renderer.

The ``del`` token type maps to :meth:`Renderer.delete` (``del`` is a Python
keyword); the parser dispatches accordingly.
"""

from __future__ import annotations

from .defaults import _defaults
from .helpers import clean_url, escape_html_entities
from .rules import other


class Renderer:
    def __init__(self, options=None):
        self.options = options or _defaults
        self.parser = None  # set by the parser

    def space(self, token):
        return ""

    def code(self, token):
        text = token["text"]
        lang = token.get("lang") or ""
        escaped = token.get("escaped", False)

        match = other["notSpaceStart"].match(lang)
        lang_string = match.group(0) if match else ""

        code = other["endingNewline"].sub("", text) + "\n"

        if not lang_string:
            body = code if escaped else escape_html_entities(code, True)
            return "<pre><code>" + body + "</code></pre>\n"

        body = code if escaped else escape_html_entities(code, True)
        return (
            '<pre><code class="language-'
            + escape_html_entities(lang_string)
            + '">'
            + body
            + "</code></pre>\n"
        )

    def blockquote(self, token):
        body = self.parser.parse(token["tokens"])
        return f"<blockquote>\n{body}</blockquote>\n"

    def html(self, token):
        return token["text"]

    def definition(self, token):
        return ""

    def_ = definition

    def heading(self, token):
        depth = token["depth"]
        return f"<h{depth}>{self.parser.parse_inline(token['tokens'])}</h{depth}>\n"

    def hr(self, token):
        return "<hr>\n"

    def list(self, token):
        ordered = token["ordered"]
        start = token["start"]

        body = ""
        for item in token["items"]:
            body += self.listitem(item)

        tag = "ol" if ordered else "ul"
        start_attr = f' start="{start}"' if (ordered and start != 1) else ""
        return f"<{tag}{start_attr}>\n{body}</{tag}>\n"

    def listitem(self, item):
        return f"<li>{self.parser.parse(item['tokens'])}</li>\n"

    def checkbox(self, token):
        return (
            "<input "
            + ('checked="" ' if token["checked"] else "")
            + 'disabled="" type="checkbox"> '
        )

    def paragraph(self, token):
        return f"<p>{self.parser.parse_inline(token['tokens'])}</p>\n"

    def table(self, token):
        cell = ""
        for th in token["header"]:
            cell += self.tablecell(th)
        header = self.tablerow({"text": cell})

        body = ""
        for row in token["rows"]:
            cell = ""
            for td in row:
                cell += self.tablecell(td)
            body += self.tablerow({"text": cell})
        if body:
            body = f"<tbody>{body}</tbody>"

        return (
            "<table>\n<thead>\n" + header + "</thead>\n" + body + "</table>\n"
        )

    def tablerow(self, token):
        return f"<tr>\n{token['text']}</tr>\n"

    def tablecell(self, token):
        content = self.parser.parse_inline(token["tokens"])
        tag = "th" if token["header"] else "td"
        align = token.get("align")
        open_tag = f'<{tag} align="{align}">' if align else f"<{tag}>"
        return open_tag + content + f"</{tag}>\n"

    def strong(self, token):
        return f"<strong>{self.parser.parse_inline(token['tokens'])}</strong>"

    def em(self, token):
        return f"<em>{self.parser.parse_inline(token['tokens'])}</em>"

    def codespan(self, token):
        return f"<code>{escape_html_entities(token['text'], True)}</code>"

    def br(self, token):
        return "<br>"

    def delete(self, token):
        return f"<del>{self.parser.parse_inline(token['tokens'])}</del>"

    del_ = delete

    def link(self, token):
        href = token["href"]
        title = token.get("title")
        text = self.parser.parse_inline(token["tokens"])
        clean_href = clean_url(href)
        if clean_href is None:
            return text
        href = clean_href
        out = '<a href="' + href + '"'
        if title:
            out += ' title="' + escape_html_entities(title) + '"'
        out += ">" + text + "</a>"
        return out

    def image(self, token):
        href = token["href"]
        title = token.get("title")
        text = token["text"]
        if token.get("tokens"):
            text = self.parser.parse_inline(token["tokens"], self.parser.text_renderer)
        clean_href = clean_url(href)
        if clean_href is None:
            return escape_html_entities(text)
        href = clean_href
        out = f'<img src="{href}" alt="{escape_html_entities(text)}"'
        if title:
            out += f' title="{escape_html_entities(title)}"'
        out += ">"
        return out

    def text(self, token):
        if token.get("tokens"):
            return self.parser.parse_inline(token["tokens"])
        if token.get("escaped"):
            return token["text"]
        return escape_html_entities(token["text"])

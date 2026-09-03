# Ported from markedjs/marked (MIT). Mirrors src/Parser.ts.
"""Turn a token list into rendered output."""

from __future__ import annotations

from .defaults import _defaults
from .renderer import Renderer
from .text_renderer import TextRenderer


class Parser:
    def __init__(self, options=None):
        self.options = options or _defaults
        self.renderer = self.options.get("renderer") or Renderer()
        self.renderer.options = self.options
        self.renderer.parser = self
        self.text_renderer = TextRenderer()

    @staticmethod
    def parse_static(tokens, options=None):
        return Parser(options).parse(tokens)

    @staticmethod
    def parse_inline_static(tokens, options=None):
        return Parser(options).parse_inline(tokens)

    def parse(self, tokens):
        self.renderer.parser = self
        out = ""
        renderer = self.renderer

        for token in tokens:
            ttype = token["type"]
            if ttype == "space":
                out += renderer.space(token)
            elif ttype == "hr":
                out += renderer.hr(token)
            elif ttype == "heading":
                out += renderer.heading(token)
            elif ttype == "code":
                out += renderer.code(token)
            elif ttype == "table":
                out += renderer.table(token)
            elif ttype == "blockquote":
                out += renderer.blockquote(token)
            elif ttype == "list":
                out += renderer.list(token)
            elif ttype == "checkbox":
                out += renderer.checkbox(token)
            elif ttype == "html":
                out += renderer.html(token)
            elif ttype == "def":
                out += renderer.definition(token)
            elif ttype == "paragraph":
                out += renderer.paragraph(token)
            elif ttype == "text":
                out += renderer.text(token)
            else:
                err = f'Token with "{ttype}" type was not found.'
                if self.options.get("silent"):
                    return ""
                raise ValueError(err)
        return out

    def parse_inline(self, tokens, renderer=None):
        self.renderer.parser = self
        renderer = renderer or self.renderer
        out = ""

        for token in tokens:
            ttype = token["type"]
            if ttype == "escape":
                out += renderer.text(token)
            elif ttype == "html":
                out += renderer.html(token)
            elif ttype == "link":
                out += renderer.link(token)
            elif ttype == "image":
                out += renderer.image(token)
            elif ttype == "checkbox":
                out += renderer.checkbox(token)
            elif ttype == "strong":
                out += renderer.strong(token)
            elif ttype == "em":
                out += renderer.em(token)
            elif ttype == "codespan":
                out += renderer.codespan(token)
            elif ttype == "br":
                out += renderer.br(token)
            elif ttype == "del":
                out += renderer.delete(token)
            elif ttype == "text":
                out += renderer.text(token)
            else:
                err = f'Token with "{ttype}" type was not found.'
                if self.options.get("silent"):
                    return ""
                raise ValueError(err)
        return out

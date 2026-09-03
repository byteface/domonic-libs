# Ported from markedjs/marked (MIT). Mirrors src/TextRenderer.ts.
"""Renderer that returns only the textual part of a token (used for image alt)."""

from __future__ import annotations


class TextRenderer:
    def strong(self, token):
        return token["text"]

    def em(self, token):
        return token["text"]

    def codespan(self, token):
        return token["text"]

    def delete(self, token):
        return token["text"]

    del_ = delete

    def html(self, token):
        return token["text"]

    def text(self, token):
        return token["text"]

    def link(self, token):
        return "" + token["text"]

    def image(self, token):
        return "" + token["text"]

    def br(self, token=None):
        return ""

    def checkbox(self, token):
        return token["raw"]

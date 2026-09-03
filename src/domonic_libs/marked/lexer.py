# Ported from markedjs/marked (MIT). Mirrors src/Lexer.ts.
"""Block + inline lexing: Markdown source -> token list."""

from __future__ import annotations

from .defaults import _defaults
from .rules import block, inline, other
from .tokenizer import Tokenizer


class Lexer:
    def __init__(self, options=None):
        self.tokens = []
        self.tokens_links = {}
        self.options = options or _defaults
        self.options.setdefault("tokenizer", None)
        self.tokenizer = self.options.get("tokenizer") or Tokenizer()
        self.tokenizer.options = self.options
        self.tokenizer.lexer = self
        self.inline_queue = []
        self.state = {
            "inLink": False,
            "inRawBlock": False,
            "linkEmitted": False,
            "top": True,
        }

        rules = {"other": other, "block": block["normal"], "inline": inline["normal"]}
        if self.options.get("pedantic"):
            rules["block"] = block["pedantic"]
            rules["inline"] = inline["pedantic"]
        elif self.options.get("gfm"):
            rules["block"] = block["gfm"]
            rules["inline"] = inline["breaks"] if self.options.get("breaks") else inline["gfm"]
        self.tokenizer.rules = rules

    @staticmethod
    def lex(src, options=None):
        return Lexer(options).run(src)

    @staticmethod
    def lex_inline(src, options=None):
        return Lexer(options).inline_tokens(src)

    def run(self, src):
        src = other["carriageReturn"].sub("\n", src)
        self.block_tokens(src, self.tokens)
        for entry in self.inline_queue:
            self.inline_tokens(entry["src"], entry["tokens"])
        self.inline_queue = []
        return self.tokens

    # -- block ----------------------------------------------------------

    def block_tokens(self, src, tokens=None, last_paragraph_clipped=False):
        if tokens is None:
            tokens = []
        self.tokenizer.lexer = self
        if self.options.get("pedantic"):
            src = other["spaceLine"].sub("", other["tabCharGlobal"].sub("    ", src))

        src_length = float("inf")
        while src:
            if len(src) < src_length:
                src_length = len(src)
            else:
                self._infinite_loop_error(src)
                break

            # newline
            token = self.tokenizer.space(src)
            if token:
                src = src[len(token["raw"]):]
                last = tokens[-1] if tokens else None
                if len(token["raw"]) == 1 and last is not None:
                    last["raw"] += "\n"
                else:
                    tokens.append(token)
                continue

            # code
            token = self.tokenizer.code(src)
            if token:
                src = src[len(token["raw"]):]
                last = tokens[-1] if tokens else None
                if last is not None and last["type"] in ("paragraph", "text"):
                    last["raw"] += ("" if last["raw"].endswith("\n") else "\n") + token["raw"]
                    last["text"] += "\n" + token["text"]
                    self.inline_queue[-1]["src"] = last["text"]
                else:
                    tokens.append(token)
                continue

            for name in ("fences", "heading", "hr", "blockquote", "list", "html"):
                token = getattr(self.tokenizer, name)(src)
                if token:
                    src = src[len(token["raw"]):]
                    tokens.append(token)
                    break
            if token:
                continue

            # def
            token = self.tokenizer.definition(src)
            if token:
                src = src[len(token["raw"]):]
                last = tokens[-1] if tokens else None
                if last is not None and last["type"] in ("paragraph", "text"):
                    last["raw"] += ("" if last["raw"].endswith("\n") else "\n") + token["raw"]
                    last["text"] += "\n" + token["raw"]
                    self.inline_queue[-1]["src"] = last["text"]
                elif token["tag"] not in self.tokens_links:
                    self.tokens_links[token["tag"]] = {
                        "href": token["href"],
                        "title": token["title"],
                    }
                    tokens.append(token)
                continue

            # table
            token = self.tokenizer.table(src)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # lheading
            token = self.tokenizer.lheading(src)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # paragraph
            cut_src = src
            if self.state["top"]:
                token = self.tokenizer.paragraph(cut_src)
                if token:
                    last = tokens[-1] if tokens else None
                    if last_paragraph_clipped and last is not None and last["type"] == "paragraph":
                        last["raw"] += ("" if last["raw"].endswith("\n") else "\n") + token["raw"]
                        last["text"] += "\n" + token["text"]
                        self.inline_queue.pop()
                        self.inline_queue[-1]["src"] = last["text"]
                    else:
                        tokens.append(token)
                    last_paragraph_clipped = len(cut_src) != len(src)
                    src = src[len(token["raw"]):]
                    continue

            # text
            token = self.tokenizer.text(src)
            if token:
                src = src[len(token["raw"]):]
                last = tokens[-1] if tokens else None
                if last is not None and last["type"] == "text":
                    last["raw"] += ("" if last["raw"].endswith("\n") else "\n") + token["raw"]
                    last["text"] += "\n" + token["text"]
                    self.inline_queue.pop()
                    self.inline_queue[-1]["src"] = last["text"]
                else:
                    tokens.append(token)
                continue

            if src:
                self._infinite_loop_error(src)
                break

        self.state["top"] = True
        return tokens

    def inline(self, src, tokens=None):
        if tokens is None:
            tokens = []
        self.inline_queue.append({"src": src, "tokens": tokens})
        return tokens

    # -- inline ---------------------------------------------------------

    def _link_in_text(self, text):
        if "[" not in text:
            return False
        link_rule = self.tokenizer.rules["inline"]["link"]
        for m in self.tokenizer.rules["inline"]["blockSkip"].finditer(text):
            if link_rule.match(m.group(0)) and (m.start() == 0 or text[m.start() - 1] != "!"):
                return True
        for m in self.tokenizer.rules["inline"]["reflinkSearch"].finditer(text):
            match0 = m.group(0)
            ref_start = match0.rfind("[")
            if match0[0] == "!" or match0[ref_start + 1 : -1] not in self.tokens_links:
                continue
            if ref_start > 1 and self._link_in_text(match0[1 : ref_start - 1]):
                continue
            return True
        return False

    def inline_tokens(self, src, tokens=None):
        if tokens is None:
            tokens = []
        self.tokenizer.lexer = self
        masked_src = src

        if self.tokens_links and "[" in src:
            reflink_search = self.tokenizer.rules["inline"]["reflinkSearch"]

            def mask_reflink(m):
                match0 = m.group(0)
                ref_start = match0.rfind("[")
                if match0[ref_start + 1 : -1] not in self.tokens_links:
                    return match0
                if ref_start > 1 and match0[0] != "!":
                    text = match0[1 : ref_start - 1]
                    if self._link_in_text(text):
                        return (
                            "["
                            + reflink_search.sub(mask_reflink, text)
                            + "]["
                            + "a" * (len(match0) - ref_start - 2)
                            + "]"
                        )
                return "[" + "a" * (len(match0) - 2) + "]"

            masked_src = reflink_search.sub(mask_reflink, masked_src)

        masked_src = self.tokenizer.rules["inline"]["anyPunctuation"].sub(
            lambda m: "+" * len(m.group(0)), masked_src
        )

        def mask_block(m):
            match0 = m.group(0)
            context = m.group(1)
            offset = len(context) if context else 0
            return match0[:offset] + "[" + "a" * (len(match0) - offset - 2) + "]"

        masked_src = self.tokenizer.rules["inline"]["blockSkip"].sub(mask_block, masked_src)

        keep_prev_char = False
        prev_char = ""
        src_length = float("inf")
        while src:
            if len(src) < src_length:
                src_length = len(src)
            else:
                self._infinite_loop_error(src)
                break

            if not keep_prev_char:
                prev_char = ""
            keep_prev_char = False

            # escape
            token = self.tokenizer.escape(src)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # tag
            token = self.tokenizer.tag(src)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # link
            token = self.tokenizer.link(src)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # reflink, nolink
            token = self.tokenizer.reflink(src, self.tokens_links)
            if token:
                src = src[len(token["raw"]):]
                last = tokens[-1] if tokens else None
                if token["type"] == "text" and last is not None and last["type"] == "text":
                    last["raw"] += token["raw"]
                    last["text"] += token["text"]
                else:
                    tokens.append(token)
                continue

            # em & strong
            token = self.tokenizer.em_strong(src, masked_src, prev_char)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # code
            token = self.tokenizer.codespan(src)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # br
            token = self.tokenizer.br(src)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # del (gfm)
            token = self.tokenizer.delete(src, masked_src, prev_char)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # autolink
            token = self.tokenizer.autolink(src)
            if token:
                src = src[len(token["raw"]):]
                tokens.append(token)
                continue

            # url (gfm)
            if not self.state["inLink"]:
                token = self.tokenizer.url(src)
                if token:
                    src = src[len(token["raw"]):]
                    tokens.append(token)
                    continue

            # text
            cut_src = src
            token = self.tokenizer.inline_text(cut_src)
            if token:
                src = src[len(token["raw"]):]
                if token["raw"][-1:] != "_":
                    prev_char = token["raw"][-1:]
                keep_prev_char = True
                last = tokens[-1] if tokens else None
                if last is not None and last["type"] == "text":
                    last["raw"] += token["raw"]
                    last["text"] += token["text"]
                else:
                    tokens.append(token)
                continue

            if src:
                self._infinite_loop_error(src)
                break

        return tokens

    def _infinite_loop_error(self, src):
        byte = ord(src[0]) if src else 0
        msg = f"Infinite loop on byte: {byte}"
        if self.options.get("silent"):
            return
        raise RuntimeError(msg)

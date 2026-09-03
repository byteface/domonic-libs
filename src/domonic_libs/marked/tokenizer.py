# Ported from markedjs/marked (MIT). Mirrors src/Tokenizer.ts.
"""Recognises one Markdown construct at a time from the head of the source."""

from __future__ import annotations

import re

from ._unicode import is_alpha_numeric
from .defaults import _defaults
from .helpers import (
    expand_tabs,
    find_closing_bracket,
    rtrim,
    split_cells,
    trim_trailing_blank_lines,
)


def _sub_group1(regex, string):
    """``string.replace(regex, '$1')`` -- keep only capture group 1."""
    return regex.sub(lambda m: m.group(1) or "", string)


def _grp(match, index):
    """``match[index]`` tolerating regex variants with fewer groups."""
    return match.group(index) if index <= match.re.groups else None


def _r_delim(match):
    for i in range(1, 7):
        value = _grp(match, i)
        if value:
            return value, i
    return None, 0


def output_link(cap, link, raw, lexer, rules):
    href = link["href"]
    title = link.get("title") or None
    text = _sub_group1(rules["other"]["outputLinkReplace"], cap.group(1))
    is_image = cap.group(0)[0] == "!"

    lexer.state["inLink"] = True
    outer_link_emitted = lexer.state["linkEmitted"]
    outer_in_raw_block = lexer.state["inRawBlock"]
    lexer.state["linkEmitted"] = False
    tokens = lexer.inline_tokens(text)
    text_has_link = lexer.state["linkEmitted"]
    lexer.state["linkEmitted"] = outer_link_emitted
    lexer.state["inLink"] = False

    if not is_image:
        if text_has_link:
            lexer.state["inRawBlock"] = outer_in_raw_block
            return None
        lexer.state["linkEmitted"] = True

    return {
        "type": "image" if is_image else "link",
        "raw": raw,
        "href": href,
        "title": title,
        "text": text,
        "tokens": tokens,
    }


def indent_code_compensation(raw, text, rules):
    match = rules["other"]["indentCodeCompensation"].search(raw)
    if match is None:
        return text
    indent_to_code = match.group(1)

    lines = []
    for node in text.split("\n"):
        m = rules["other"]["beginningSpace"].match(node)
        if m is None:
            lines.append(node)
            continue
        indent_in_node = m.group(0)
        if len(indent_in_node) >= len(indent_to_code):
            lines.append(node[len(indent_to_code):])
        else:
            lines.append(node)
    return "\n".join(lines)


class Tokenizer:
    def __init__(self, options=None):
        self.options = options or _defaults
        self.rules = None  # set by the lexer
        self.lexer = None  # set by the lexer

    # -- block --------------------------------------------------------------

    def space(self, src):
        cap = self.rules["block"]["newline"].match(src)
        if cap and len(cap.group(0)) > 0:
            return {"type": "space", "raw": cap.group(0)}
        return None

    def code(self, src):
        cap = self.rules["block"]["code"].match(src)
        if cap:
            raw = cap.group(0) if self.options.get("pedantic") else trim_trailing_blank_lines(cap.group(0))
            text = self.rules["other"]["codeRemoveIndent"].sub("", raw)
            return {
                "type": "code",
                "raw": raw,
                "codeBlockStyle": "indented",
                "text": text,
            }
        return None

    def fences(self, src):
        cap = self.rules["block"]["fences"].match(src)
        if cap:
            raw = cap.group(0)
            text = indent_code_compensation(raw, cap.group(3) or "", self.rules)
            lang = cap.group(2)
            if lang:
                lang = _sub_group1(self.rules["inline"]["anyPunctuation"], lang.strip())
            return {"type": "code", "raw": raw, "lang": lang, "text": text}
        return None

    def heading(self, src):
        cap = self.rules["block"]["heading"].match(src)
        if cap:
            text = cap.group(2).strip()
            if self.rules["other"]["endingHash"].search(text):
                trimmed = rtrim(text, "#")
                if self.options.get("pedantic"):
                    text = trimmed.strip()
                elif not trimmed or self.rules["other"]["endingSpaceChar"].search(trimmed):
                    text = trimmed.strip()
            return {
                "type": "heading",
                "raw": rtrim(cap.group(0), "\n"),
                "depth": len(cap.group(1)),
                "text": text,
                "tokens": self.lexer.inline(text),
            }
        return None

    def hr(self, src):
        cap = self.rules["block"]["hr"].match(src)
        if cap:
            return {"type": "hr", "raw": rtrim(cap.group(0), "\n")}
        return None

    def blockquote(self, src):
        cap = self.rules["block"]["blockquote"].match(src)
        if not cap:
            return None

        lines = rtrim(cap.group(0), "\n").split("\n")
        raw = ""
        text = ""
        tokens = []

        while len(lines) > 0:
            in_blockquote = False
            current_lines = []

            i = 0
            while i < len(lines):
                if self.rules["other"]["blockquoteStart"].match(lines[i]):
                    current_lines.append(lines[i])
                    in_blockquote = True
                elif not in_blockquote:
                    current_lines.append(lines[i])
                else:
                    break
                i += 1
            lines = lines[i:]

            current_raw = "\n".join(current_lines)
            current_text = self.rules["other"]["blockquoteSetextReplace2"].sub(
                "",
                self.rules["other"]["blockquoteSetextReplace"].sub("\n    \\1", current_raw),
            )
            raw = f"{raw}\n{current_raw}" if raw else current_raw
            text = f"{text}\n{current_text}" if text else current_text

            top = self.lexer.state["top"]
            self.lexer.state["top"] = True
            self.lexer.block_tokens(current_text, tokens, True)
            self.lexer.state["top"] = top

            if len(lines) == 0:
                break

            last_token = tokens[-1] if tokens else None

            if last_token and last_token["type"] == "code":
                break
            elif last_token and last_token["type"] == "blockquote":
                old_token = last_token
                continuation = "\n".join(lines)
                new_text = old_token["raw"] + "\n" + self.rules["other"]["blockquoteSetextReplace2"].sub("", continuation)
                new_token = self.blockquote(new_text)
                tokens[-1] = new_token
                raw = f"{raw}\n{continuation}"
                text = text[: len(text) - len(old_token["text"])] + new_token["text"]
                break
            elif last_token and last_token["type"] == "list":
                old_token = last_token
                new_text = old_token["raw"] + "\n" + "\n".join(lines)
                new_token = self.list(new_text)
                tokens[-1] = new_token
                raw = raw[: len(raw) - len(last_token["raw"])] + new_token["raw"]
                text = text[: len(text) - len(old_token["raw"])] + new_token["raw"]
                lines = new_text[len(tokens[-1]["raw"]):].split("\n")
                continue

        return {"type": "blockquote", "raw": raw, "tokens": tokens, "text": text}

    def list(self, src):
        cap = self.rules["block"]["list"].match(src)
        if not cap:
            return None

        bull = cap.group(1).strip()
        is_ordered = len(bull) > 1

        lst = {
            "type": "list",
            "raw": "",
            "ordered": is_ordered,
            "start": int(bull[:-1]) if is_ordered else "",
            "loose": False,
            "items": [],
        }

        bull = ("\\d{1,9}\\" + bull[-1]) if is_ordered else ("\\" + bull)
        if self.options.get("pedantic"):
            bull = bull if is_ordered else "[*+-]"

        item_regex = self.rules["other"]["listItemRegex"](bull)
        ends_with_blank_line = False

        while src:
            end_early = False
            raw = ""
            item_contents = ""
            cap = item_regex.match(src)
            if not cap:
                break

            if self.rules["block"]["hr"].match(src):
                break

            raw = cap.group(0)
            src = src[len(raw):]

            line = expand_tabs(cap.group(2).split("\n", 1)[0], len(cap.group(1)))
            next_line = src.split("\n", 1)[0]
            blank_line = not line.strip()

            if self.options.get("pedantic"):
                indent = 2
                item_contents = line.lstrip()
            elif blank_line:
                indent = len(cap.group(1)) + 1
            else:
                m = self.rules["other"]["nonSpaceChar"].search(line)
                indent = m.start() if m else -1
                indent = 1 if indent > 4 else indent
                item_contents = line[indent:]
                indent += len(cap.group(1))

            if blank_line and self.rules["other"]["blankLine"].match(next_line):
                raw += next_line + "\n"
                src = src[len(next_line) + 1:]
                end_early = True

            if not end_early:
                next_bullet_regex = self.rules["other"]["nextBulletRegex"](indent)
                hr_regex = self.rules["other"]["hrRegex"](indent)
                fences_begin_regex = self.rules["other"]["fencesBeginRegex"](indent)
                heading_begin_regex = self.rules["other"]["headingBeginRegex"](indent)
                html_begin_regex = self.rules["other"]["htmlBeginRegex"](indent)
                blockquote_begin_regex = self.rules["other"]["blockquoteBeginRegex"](indent)

                while src:
                    raw_line = src.split("\n", 1)[0]
                    next_line = raw_line

                    if self.options.get("pedantic"):
                        next_line = self.rules["other"]["listReplaceNesting"].sub("  ", next_line)
                        next_line_without_tabs = next_line
                    else:
                        next_line_without_tabs = self.rules["other"]["tabCharGlobal"].sub("    ", next_line)

                    if fences_begin_regex.match(next_line):
                        break
                    if heading_begin_regex.match(next_line):
                        break
                    if html_begin_regex.match(next_line):
                        break
                    if blockquote_begin_regex.match(next_line):
                        break
                    if next_bullet_regex.match(next_line):
                        break
                    if hr_regex.match(next_line):
                        break

                    m = self.rules["other"]["nonSpaceChar"].search(next_line_without_tabs)
                    search_idx = m.start() if m else -1
                    if search_idx >= indent or not next_line.strip():
                        item_contents += "\n" + next_line_without_tabs[indent:]
                    else:
                        if blank_line:
                            break
                        lm = self.rules["other"]["nonSpaceChar"].search(
                            self.rules["other"]["tabCharGlobal"].sub("    ", line)
                        )
                        if (lm.start() if lm else -1) >= 4:
                            break
                        if fences_begin_regex.match(line):
                            break
                        if heading_begin_regex.match(line):
                            break
                        if hr_regex.match(line):
                            break
                        item_contents += "\n" + next_line

                    blank_line = not next_line.strip()
                    raw += raw_line + "\n"
                    src = src[len(raw_line) + 1:]
                    line = next_line_without_tabs[indent:]

            if not lst["loose"]:
                if ends_with_blank_line:
                    lst["loose"] = True
                elif self.rules["other"]["doubleBlankLine"].search(raw):
                    ends_with_blank_line = True

            lst["items"].append(
                {
                    "type": "list_item",
                    "raw": raw,
                    "task": bool(self.options.get("gfm"))
                    and bool(self.rules["other"]["listIsTask"].match(item_contents)),
                    "loose": False,
                    "text": item_contents,
                    "tokens": [],
                }
            )
            lst["raw"] += raw

        if lst["items"]:
            last_item = lst["items"][-1]
            last_item["raw"] = last_item["raw"].rstrip()
            last_item["text"] = last_item["text"].rstrip()
        else:
            return None
        lst["raw"] = lst["raw"].rstrip()

        for item in lst["items"]:
            self.lexer.state["top"] = False
            item["tokens"] = self.lexer.block_tokens(item["text"], [])
            if not lst["loose"]:
                spacers = [t for t in item["tokens"] if t["type"] == "space"]
                has_multiple = len(spacers) > 0 and any(
                    self.rules["other"]["anyLine"].search(t["raw"]) for t in spacers
                )
                lst["loose"] = has_multiple

        for item in lst["items"]:
            item_token = item["tokens"][0] if item["tokens"] else None
            if item["task"] and item_token and item_token["type"] in ("text", "paragraph"):
                item["text"] = self.rules["other"]["listReplaceTask"].sub("", item["text"])
                item_token["raw"] = self.rules["other"]["listReplaceTask"].sub("", item_token["raw"])
                item_token["text"] = self.rules["other"]["listReplaceTask"].sub("", item_token["text"])
                for k in range(len(self.lexer.inline_queue) - 1, -1, -1):
                    if self.rules["other"]["listIsTask"].match(self.lexer.inline_queue[k]["src"]):
                        self.lexer.inline_queue[k]["src"] = self.rules["other"]["listReplaceTask"].sub(
                            "", self.lexer.inline_queue[k]["src"]
                        )
                        break

                task_raw = self.rules["other"]["listTaskCheckbox"].search(item["raw"])
                if task_raw:
                    checkbox_token = {
                        "type": "checkbox",
                        "raw": task_raw.group(0) + " ",
                        "checked": task_raw.group(0) != "[ ]",
                    }
                    item["checked"] = checkbox_token["checked"]
                    if lst["loose"]:
                        t0 = item["tokens"][0] if item["tokens"] else None
                        if t0 and t0["type"] in ("paragraph", "text") and t0.get("tokens") is not None:
                            t0["raw"] = checkbox_token["raw"] + t0["raw"]
                            t0["text"] = checkbox_token["raw"] + t0["text"]
                            t0["tokens"].insert(0, checkbox_token)
                        else:
                            item["tokens"].insert(
                                0,
                                {
                                    "type": "paragraph",
                                    "raw": checkbox_token["raw"],
                                    "text": checkbox_token["raw"],
                                    "tokens": [checkbox_token],
                                },
                            )
                    else:
                        item["tokens"].insert(0, checkbox_token)
            elif item["task"]:
                item["task"] = False

        if lst["loose"]:
            for item in lst["items"]:
                item["loose"] = True
                for token in item["tokens"]:
                    if token["type"] == "text":
                        token["type"] = "paragraph"

        return lst

    def html(self, src):
        cap = self.rules["block"]["html"].match(src)
        if cap:
            raw = trim_trailing_blank_lines(cap.group(0))
            return {
                "type": "html",
                "block": True,
                "raw": raw,
                "pre": cap.group(1) in ("pre", "script", "style"),
                "text": raw,
            }
        return None

    def definition(self, src):
        cap = self.rules["block"]["def"].match(src)
        if cap:
            tag = self.rules["other"]["multipleSpaceGlobal"].sub(" ", cap.group(1).lower())
            href = ""
            if cap.group(2):
                href = _sub_group1(
                    self.rules["inline"]["anyPunctuation"],
                    self.rules["other"]["hrefBrackets"].sub(lambda m: m.group(1), cap.group(2)),
                )
            title = cap.group(3)
            if title:
                title = _sub_group1(self.rules["inline"]["anyPunctuation"], title[1:-1])
            return {
                "type": "def",
                "tag": tag,
                "raw": rtrim(cap.group(0), "\n"),
                "href": href,
                "title": title,
            }
        return None

    def table(self, src):
        cap = self.rules["block"]["table"].match(src)
        if not cap:
            return None
        if not self.rules["other"]["tableDelimiter"].search(cap.group(2)):
            return None

        headers = split_cells(cap.group(1))
        aligns = self.rules["other"]["tableAlignChars"].sub("", cap.group(2)).split("|")
        rows_src = cap.group(3)
        rows = (
            self.rules["other"]["tableRowBlankLine"].sub("", rows_src).split("\n")
            if rows_src and rows_src.strip()
            else []
        )

        item = {"type": "table", "raw": rtrim(cap.group(0), "\n"), "header": [], "align": [], "rows": []}

        if len(headers) != len(aligns):
            return None

        for align in aligns:
            if self.rules["other"]["tableAlignRight"].match(align):
                item["align"].append("right")
            elif self.rules["other"]["tableAlignCenter"].match(align):
                item["align"].append("center")
            elif self.rules["other"]["tableAlignLeft"].match(align):
                item["align"].append("left")
            else:
                item["align"].append(None)

        for i in range(len(headers)):
            item["header"].append(
                {
                    "text": headers[i],
                    "tokens": self.lexer.inline(headers[i]),
                    "header": True,
                    "align": item["align"][i],
                }
            )

        for row in rows:
            cells = split_cells(row, len(item["header"]))
            item["rows"].append(
                [
                    {
                        "text": cell,
                        "tokens": self.lexer.inline(cell),
                        "header": False,
                        "align": item["align"][i] if i < len(item["align"]) else None,
                    }
                    for i, cell in enumerate(cells)
                ]
            )

        return item

    def lheading(self, src):
        cap = self.rules["block"]["lheading"].match(src)
        if cap:
            text = cap.group(1).strip()
            return {
                "type": "heading",
                "raw": rtrim(cap.group(0), "\n"),
                "depth": 1 if cap.group(2)[0] == "=" else 2,
                "text": text,
                "tokens": self.lexer.inline(text),
            }
        return None

    def paragraph(self, src):
        cap = self.rules["block"]["paragraph"].match(src)
        if cap:
            g1 = cap.group(1)
            text = g1[:-1] if g1[-1:] == "\n" else g1
            return {
                "type": "paragraph",
                "raw": cap.group(0),
                "text": text,
                "tokens": self.lexer.inline(text),
            }
        return None

    def text(self, src):
        cap = self.rules["block"]["text"].match(src)
        if cap:
            return {
                "type": "text",
                "raw": cap.group(0),
                "text": cap.group(0),
                "tokens": self.lexer.inline(cap.group(0)),
            }
        return None

    # -- inline -----------------------------------------------------------

    def escape(self, src):
        cap = self.rules["inline"]["escape"].match(src)
        if cap:
            return {"type": "escape", "raw": cap.group(0), "text": cap.group(1)}
        return None

    def tag(self, src):
        cap = self.rules["inline"]["tag"].match(src)
        if cap:
            c0 = cap.group(0)
            state = self.lexer.state
            if not state["inLink"] and self.rules["other"]["startATag"].match(c0):
                state["inLink"] = True
            elif state["inLink"] and self.rules["other"]["endATag"].match(c0):
                state["inLink"] = False
            if not state["inRawBlock"] and self.rules["other"]["startPreScriptTag"].match(c0):
                state["inRawBlock"] = True
            elif state["inRawBlock"] and self.rules["other"]["endPreScriptTag"].match(c0):
                state["inRawBlock"] = False
            return {
                "type": "html",
                "raw": c0,
                "inLink": state["inLink"],
                "inRawBlock": state["inRawBlock"],
                "block": False,
                "text": c0,
            }
        return None

    def link(self, src):
        cap = self.rules["inline"]["link"].match(src)
        if not cap:
            return None

        c0, c1, c2, c3 = cap.group(0), cap.group(1), cap.group(2), _grp(cap, 3)
        trimmed_url = (c2 or "").strip()

        if not self.options.get("pedantic") and self.rules["other"]["startAngleBracket"].match(trimmed_url):
            if not self.rules["other"]["endAngleBracket"].search(trimmed_url):
                return None
            rtrim_slash = rtrim(trimmed_url[:-1], "\\")
            if (len(trimmed_url) - len(rtrim_slash)) % 2 == 0:
                return None
        else:
            last_paren_index = find_closing_bracket(c2 or "", "()")
            if last_paren_index == -2:
                return None
            if last_paren_index > -1:
                start = 5 if c0.find("!") == 0 else 4
                link_len = start + len(c1) + last_paren_index
                c2 = c2[:last_paren_index]
                c0 = c0[:link_len].strip()
                c3 = ""

        href = c2 or ""
        title = ""
        if self.options.get("pedantic"):
            link_m = self.rules["other"]["pedanticHrefTitle"].match(href)
            if link_m:
                href = link_m.group(1)
                title = link_m.group(3)
        else:
            title = c3[1:-1] if c3 else ""

        href = href.strip()
        if self.rules["other"]["startAngleBracket"].match(href):
            if self.options.get("pedantic") and not self.rules["other"]["endAngleBracket"].search(trimmed_url):
                href = href[1:]
            else:
                href = href[1:-1]

        # rebuild cap groups for output_link (needs group(0) and group(1))
        rebuilt = _FakeMatch(c0, c1)
        return output_link(
            rebuilt,
            {
                "href": _sub_group1(self.rules["inline"]["anyPunctuation"], href) if href else href,
                "title": _sub_group1(self.rules["inline"]["anyPunctuation"], title) if title else title,
            },
            c0,
            self.lexer,
            self.rules,
        )

    def reflink(self, src, links):
        cap = self.rules["inline"]["reflink"].match(src)
        if not cap:
            cap = self.rules["inline"]["nolink"].match(src)
        if not cap:
            return None

        raw_key = cap.group(2) if cap.lastindex and cap.lastindex >= 2 and cap.group(2) is not None else cap.group(1)
        link_string = self.rules["other"]["multipleSpaceGlobal"].sub(" ", raw_key)
        link = links.get(link_string.lower())
        if not link:
            text = cap.group(0)[0]
            return {"type": "text", "raw": text, "text": text}
        return output_link(_FakeMatch(cap.group(0), cap.group(1)), link, cap.group(0), self.lexer, self.rules)

    def em_strong(self, src, masked_src, prev_char=""):
        l_match = self.rules["inline"]["emStrongLDelim"].match(src)
        if not l_match:
            return None
        if not (l_match.group(1) or l_match.group(2) or l_match.group(3) or l_match.group(4)):
            return None
        if l_match.group(4) and prev_char and is_alpha_numeric(prev_char):
            return None

        next_char = l_match.group(1) or l_match.group(3) or ""

        if next_char and prev_char and not self.rules["inline"]["punctuation"].match(prev_char):
            return None

        l_length = len(l_match.group(0)) - 1
        delim_total = l_length
        mid_delim_total = 0

        delim_char = l_match.group(0)[0]
        mid_run = prev_char == delim_char
        end_reg = (
            self.rules["inline"]["emStrongRDelimAst"]
            if delim_char == "*"
            else self.rules["inline"]["emStrongRDelimUnd"]
        )

        clipped = masked_src[-(len(src)) + l_length:] if -(len(src)) + l_length != 0 else masked_src

        for r_match in end_reg.finditer(clipped):
            r_delim, _which = _r_delim(r_match)
            if not r_delim:
                continue

            r_length = len(r_delim)

            if _grp(r_match, 3) or _grp(r_match, 4):
                delim_total += r_length
                continue
            elif _grp(r_match, 5) or _grp(r_match, 6):
                if l_length % 3 and not ((l_length + r_length) % 3):
                    mid_delim_total += r_length
                    continue
                if mid_run:
                    break

            delim_total -= r_length
            if delim_total > 0:
                continue

            r_length = min(r_length, r_length + delim_total + mid_delim_total)
            last_char_length = len(r_match.group(0)[0])
            raw = src[: l_length + r_match.start() + last_char_length + r_length]

            if min(l_length, r_length) % 2:
                text = raw[1:-1]
                return {
                    "type": "em",
                    "raw": raw,
                    "text": text,
                    "tokens": self.lexer.inline_tokens(text),
                }

            text = raw[2:-2]
            return {
                "type": "strong",
                "raw": raw,
                "text": text,
                "tokens": self.lexer.inline_tokens(text),
            }
        return None

    def codespan(self, src):
        cap = self.rules["inline"]["code"].match(src)
        if cap:
            text = self.rules["other"]["newLineCharGlobal"].sub(" ", cap.group(2))
            has_non_space = bool(self.rules["other"]["nonSpaceChar"].search(text))
            has_space_both_ends = bool(
                self.rules["other"]["startingSpaceChar"].search(text)
            ) and bool(self.rules["other"]["endingSpaceChar"].search(text))
            if has_non_space and has_space_both_ends:
                text = text[1:-1]
            return {"type": "codespan", "raw": cap.group(0), "text": text}
        return None

    def br(self, src):
        cap = self.rules["inline"]["br"].match(src)
        if cap:
            return {"type": "br", "raw": cap.group(0)}
        return None

    def delete(self, src, masked_src, prev_char=""):
        l_match = self.rules["inline"]["delLDelim"].match(src)
        if not l_match:
            return None

        next_char = l_match.group(1) or ""
        if next_char and prev_char and not self.rules["inline"]["punctuation"].match(prev_char):
            return None

        l_length = len(l_match.group(0)) - 1
        delim_total = l_length
        end_reg = self.rules["inline"]["delRDelim"]

        clipped = masked_src[-(len(src)) + l_length:] if -(len(src)) + l_length != 0 else masked_src

        for r_match in end_reg.finditer(clipped):
            r_delim, _which = _r_delim(r_match)
            if not r_delim:
                continue
            r_length = len(r_delim)
            if r_length != l_length:
                continue
            if _grp(r_match, 3) or _grp(r_match, 4):
                delim_total += r_length
                continue
            delim_total -= r_length
            if delim_total > 0:
                continue
            r_length = min(r_length, r_length + delim_total)
            last_char_length = len(r_match.group(0)[0])
            raw = src[: l_length + r_match.start() + last_char_length + r_length]
            text = raw[l_length:-l_length]
            return {
                "type": "del",
                "raw": raw,
                "text": text,
                "tokens": self.lexer.inline_tokens(text),
            }
        return None

    def autolink(self, src):
        cap = self.rules["inline"]["autolink"].match(src)
        if cap:
            if cap.group(2) == "@":
                text = cap.group(1)
                href = "mailto:" + text
            else:
                text = cap.group(1)
                href = text
            return {
                "type": "link",
                "raw": cap.group(0),
                "text": text,
                "href": href,
                "tokens": [{"type": "text", "raw": text, "text": text}],
            }
        return None

    def url(self, src):
        cap = self.rules["inline"]["url"].match(src)
        if not cap:
            return None
        c0 = cap.group(0)
        if cap.lastindex and cap.group(2) == "@":
            text = c0
            href = "mailto:" + text
        else:
            prev = None
            while prev != c0:
                prev = c0
                m = self.rules["inline"]["_backpedal"].match(c0)
                c0 = m.group(0) if m else ""
            text = c0
            href = ("http://" + c0) if cap.group(1) == "www." else c0
        return {
            "type": "link",
            "raw": c0,
            "text": text,
            "href": href,
            "tokens": [{"type": "text", "raw": text, "text": text}],
        }

    def inline_text(self, src):
        cap = self.rules["inline"]["text"].match(src)
        if cap:
            escaped = self.lexer.state["inRawBlock"]
            return {
                "type": "text",
                "raw": cap.group(0),
                "text": cap.group(0),
                "escaped": escaped,
            }
        return None


class _FakeMatch:
    """Minimal stand-in exposing ``group(0)`` / ``group(1)`` for output_link."""

    def __init__(self, g0, g1):
        self._g = (g0, g1)

    def group(self, i):
        return self._g[i]

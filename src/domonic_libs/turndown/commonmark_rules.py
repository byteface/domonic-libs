# Ported from mixmark-io/turndown (MIT). Mirrors src/commonmark-rules.js.
"""The default CommonMark rule set.

Each rule is a dict with ``filter`` (tag name / list / predicate) and
``replacement(content, node, options)``. ``referenceLink`` also carries an
``append`` hook and its own ``references`` buffer, matching upstream.
"""

from __future__ import annotations

import re

from .utilities import escape_markdown, node_name, repeat, trim_newlines

RULES = {}


RULES["paragraph"] = {
    "filter": "p",
    "replacement": lambda content, node, options: "\n\n" + content + "\n\n",
}


RULES["lineBreak"] = {
    "filter": "br",
    "replacement": lambda content, node, options: options["br"] + "\n",
}


def _heading(content, node, options):
    h_level = int(node_name(node)[1])
    if options["headingStyle"] == "setext" and h_level < 3:
        underline = repeat("=" if h_level == 1 else "-", len(content))
        return "\n\n" + content + "\n" + underline + "\n\n"
    return "\n\n" + repeat("#", h_level) + " " + content + "\n\n"


RULES["heading"] = {
    "filter": ["h1", "h2", "h3", "h4", "h5", "h6"],
    "replacement": _heading,
}


def _blockquote(content, node, options):
    content = re.sub(r"^", "> ", trim_newlines(content), flags=re.MULTILINE)
    return "\n\n" + content + "\n\n"


RULES["blockquote"] = {"filter": "blockquote", "replacement": _blockquote}


def _list(content, node, options):
    parent = node.parentNode
    if node_name(parent) == "LI" and parent.lastElementChild is node:
        return "\n" + content
    return "\n\n" + content + "\n\n"


RULES["list"] = {"filter": ["ul", "ol"], "replacement": _list}


def _list_item(content, node, options):
    prefix = options["bulletListMarker"] + "   "
    parent = node.parentNode
    if node_name(parent) == "OL":
        start = parent.getAttribute("start")
        index = list(parent.children).index(node)
        prefix = str(int(start) + index if start else index + 1) + ".  "

    is_paragraph = content.endswith("\n")
    content = trim_newlines(content) + ("\n" if is_paragraph else "")
    content = re.sub(r"\n", "\n" + " " * len(prefix), content)  # indent
    return prefix + content + ("\n" if node.nextSibling else "")


RULES["listItem"] = {"filter": "li", "replacement": _list_item}


def _is_indented_code_block(node, options):
    return (
        options["codeBlockStyle"] == "indented"
        and node_name(node) == "PRE"
        and node.firstChild
        and node_name(node.firstChild) == "CODE"
    )


def _indented_code_block(content, node, options):
    return (
        "\n\n    "
        + re.sub(r"\n", "\n    ", node.firstChild.textContent)
        + "\n\n"
    )


RULES["indentedCodeBlock"] = {
    "filter": _is_indented_code_block,
    "replacement": _indented_code_block,
}


def _is_fenced_code_block(node, options):
    return (
        options["codeBlockStyle"] == "fenced"
        and node_name(node) == "PRE"
        and node.firstChild
        and node_name(node.firstChild) == "CODE"
    )


def _fenced_code_block(content, node, options):
    class_name = node.firstChild.getAttribute("class") or ""
    match = re.search(r"language-(\S+)", class_name)
    language = match.group(1) if match else ""
    code = node.firstChild.textContent

    fence_char = options["fence"][0]
    fence_size = 3
    for run in re.findall("^" + re.escape(fence_char) + "{3,}", code, flags=re.MULTILINE):
        if len(run) >= fence_size:
            fence_size = len(run) + 1

    fence = repeat(fence_char, fence_size)
    return (
        "\n\n" + fence + language + "\n"
        + re.sub(r"\n$", "", code)
        + "\n" + fence + "\n\n"
    )


RULES["fencedCodeBlock"] = {
    "filter": _is_fenced_code_block,
    "replacement": _fenced_code_block,
}


RULES["horizontalRule"] = {
    "filter": "hr",
    "replacement": lambda content, node, options: "\n\n" + options["hr"] + "\n\n",
}


def _is_inline_link(node, options):
    return (
        options["linkStyle"] == "inlined"
        and node_name(node) == "A"
        and node.getAttribute("href")
    )


def _inline_link(content, node, options):
    href = _escape_link_destination(node.getAttribute("href"))
    title = _escape_link_title(_clean_attribute(node.getAttribute("title")))
    title_part = ' "' + title + '"' if title else ""
    return "[" + content + "](" + href + title_part + ")"


RULES["inlineLink"] = {"filter": _is_inline_link, "replacement": _inline_link}


def _is_reference_link(node, options):
    return (
        options["linkStyle"] == "referenced"
        and node_name(node) == "A"
        and node.getAttribute("href")
    )


def _make_reference_link_rule():
    rule = {"filter": _is_reference_link, "references": []}

    def replacement(content, node, options):
        href = _escape_link_destination(node.getAttribute("href"))
        title = _clean_attribute(node.getAttribute("title"))
        if title:
            title = ' "' + _escape_link_title(title) + '"'

        style = options["linkReferenceStyle"]
        if style == "collapsed":
            result = "[" + content + "][]"
            reference = "[" + content + "]: " + href + title
        elif style == "shortcut":
            result = "[" + content + "]"
            reference = "[" + content + "]: " + href + title
        else:
            identifier = len(rule["references"]) + 1
            result = "[" + content + "][" + str(identifier) + "]"
            reference = "[" + str(identifier) + "]: " + href + title

        rule["references"].append(reference)
        return result

    def append(options):
        references = ""
        if rule["references"]:
            references = "\n\n" + "\n".join(rule["references"]) + "\n\n"
            rule["references"] = []  # reset references
        return references

    rule["replacement"] = replacement
    rule["append"] = append
    return rule


RULES["referenceLink"] = _make_reference_link_rule()


def _emphasis(content, node, options):
    if not content.strip():
        return ""
    return options["emDelimiter"] + content + options["emDelimiter"]


RULES["emphasis"] = {"filter": ["em", "i"], "replacement": _emphasis}


def _strong(content, node, options):
    if not content.strip():
        return ""
    return options["strongDelimiter"] + content + options["strongDelimiter"]


RULES["strong"] = {"filter": ["strong", "b"], "replacement": _strong}


def _is_code(node, options):
    has_siblings = node.previousSibling or node.nextSibling
    is_code_block = node_name(node.parentNode) == "PRE" and not has_siblings
    return node_name(node) == "CODE" and not is_code_block


def _code(content, node, options):
    if not content:
        return ""
    content = re.sub(r"\r?\n|\r", " ", content)

    extra_space = " " if re.search(r"^`|^ .*?[^ ].* $|`$", content) else ""
    delimiter = "`"
    matches = re.findall(r"`+", content)
    while delimiter in matches:
        delimiter = delimiter + "`"

    return delimiter + extra_space + content + extra_space + delimiter


RULES["code"] = {"filter": _is_code, "replacement": _code}


def _image(content, node, options):
    alt = escape_markdown(_clean_attribute(node.getAttribute("alt")))
    src = _escape_link_destination(node.getAttribute("src") or "")
    title = _clean_attribute(node.getAttribute("title"))
    title_part = ' "' + _escape_link_title(title) + '"' if title else ""
    return "![" + alt + "](" + src + title_part + ")" if src else ""


RULES["image"] = {"filter": "img", "replacement": _image}


def _clean_attribute(attribute):
    return re.sub(r"(\n+\s*)+", "\n", attribute) if attribute else ""


def _escape_link_destination(destination):
    escaped = re.sub(r"([<>()])", lambda m: "\\" + m.group(1), destination)
    return "<" + escaped + ">" if " " in escaped else escaped


def _escape_link_title(title):
    return title.replace('"', '\\"')

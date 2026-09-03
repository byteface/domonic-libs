# Ported from mixmark-io/turndown (MIT). Mirrors src/turndown.js.
"""``TurndownService`` -- convert an HTML string or domonic node to Markdown."""

from __future__ import annotations

import re

from .commonmark_rules import RULES
from .node import decorate_node
from .root_node import root_node
from .rules import Rules
from .utilities import (
    escape_markdown,
    extend,
    trim_leading_newlines,
    trim_trailing_newlines,
)


def _blank_replacement(content, node, options):
    return "\n\n" if node.isBlock else ""


def _keep_replacement(content, node, options):
    return "\n\n" + node.outerHTML + "\n\n" if node.isBlock else node.outerHTML


def _default_replacement(content, node, options):
    return "\n\n" + content + "\n\n" if node.isBlock else content


_DEFAULTS = {
    "rules": RULES,
    "headingStyle": "setext",
    "hr": "* * *",
    "bulletListMarker": "*",
    "codeBlockStyle": "indented",
    "fence": "```",
    "emDelimiter": "_",
    "strongDelimiter": "**",
    "linkStyle": "inlined",
    "linkReferenceStyle": "full",
    "br": "  ",
    "preformattedCode": False,
    "blankReplacement": _blank_replacement,
    "keepReplacement": _keep_replacement,
    "defaultReplacement": _default_replacement,
}

_SNAKE = re.compile(r"_([a-z0-9])")


def _camel(key):
    return _SNAKE.sub(lambda m: m.group(1).upper(), key)


class TurndownService:
    def __init__(self, **options):
        camel_options = {_camel(key): value for key, value in options.items()}
        self.options = extend({}, _DEFAULTS, camel_options)
        self.rules = Rules(self.options)

    def turndown(self, input_value):
        """Convert an HTML string or an element/document/fragment to Markdown."""
        if not _can_convert(input_value):
            raise TypeError(
                f"{input_value} is not a string, or an element/document/fragment node."
            )

        if input_value == "":
            return ""

        output = self._process(root_node(input_value, self.options))
        return self._post_process(output)

    def use(self, plugin):
        """Add one or more plugins (a callable, or a list of callables)."""
        if isinstance(plugin, (list, tuple)):
            for item in plugin:
                self.use(item)
        elif callable(plugin):
            plugin(self)
        else:
            raise TypeError("plugin must be a Function or an Array of Functions")
        return self

    def add_rule(self, key, rule):
        self.rules.add(key, rule)
        return self

    def keep(self, filter):
        self.rules.keep(filter)
        return self

    def remove(self, filter):
        self.rules.remove(filter)
        return self

    def escape(self, string):
        return escape_markdown(string)

    # camelCase aliases so turndown.js plugins port with minimal edits
    addRule = add_rule

    # -- private ----------------------------------------------------------

    def _process(self, parent_node):
        output = ""
        for node in list(parent_node.childNodes):
            node = decorate_node(node, self.options)

            replacement = ""
            if node.nodeType == 3:
                value = node.nodeValue or ""
                replacement = value if node.isCode else self.escape(value)
            elif node.nodeType == 1:
                replacement = self._replacement_for_node(node)

            output = _join(output, replacement)
        return output

    def _post_process(self, output):
        state = {"output": output}

        def visit(rule, _index):
            append = rule.get("append") if isinstance(rule, dict) else None
            if callable(append):
                state["output"] = _join(state["output"], append(self.options))

        self.rules.for_each(visit)
        result = re.sub(r"^[\t\r\n]+", "", state["output"])
        result = re.sub(r"[\t\r\n\s]+$", "", result)
        return result

    def _replacement_for_node(self, node):
        rule = self.rules.for_node(node)
        content = self._process(node)
        whitespace = node.flankingWhitespace
        if whitespace["leading"] or whitespace["trailing"]:
            content = content.strip()
        return (
            whitespace["leading"]
            + rule["replacement"](content, node, self.options)
            + whitespace["trailing"]
        )


def _join(output, replacement):
    s1 = trim_trailing_newlines(output)
    s2 = trim_leading_newlines(replacement)
    nls = max(len(output) - len(s1), len(replacement) - len(s2))
    separator = "\n\n"[:nls]
    return s1 + separator + s2


def _can_convert(input_value):
    if input_value is None:
        return False
    if isinstance(input_value, str):
        return True
    node_type = getattr(input_value, "nodeType", None)
    return node_type in (1, 9, 11)


def turndown(value, **options):
    return TurndownService(**options).turndown(value)

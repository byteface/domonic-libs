# Ported from mixmark-io/turndown (MIT). Mirrors src/rules.js.
"""The ordered collection of rules that map DOM nodes to Markdown."""

from __future__ import annotations

from .utilities import node_name


class Rules:
    def __init__(self, options):
        self.options = options
        self._keep = []
        self._remove = []

        self.blank_rule = {"replacement": options["blankReplacement"]}
        self.keep_replacement = options["keepReplacement"]
        self.default_rule = {"replacement": options["defaultReplacement"]}

        self.array = [options["rules"][key] for key in options["rules"]]

    def add(self, key, rule):
        self.array.insert(0, rule)

    def keep(self, filter):
        self._keep.insert(
            0, {"filter": filter, "replacement": self.keep_replacement}
        )

    def remove(self, filter):
        self._remove.insert(
            0, {"filter": filter, "replacement": lambda content, node, options: ""}
        )

    def for_node(self, node):
        if node.isBlank:
            return self.blank_rule

        rule = _find_rule(self.array, node, self.options)
        if rule is not None:
            return rule
        rule = _find_rule(self._keep, node, self.options)
        if rule is not None:
            return rule
        rule = _find_rule(self._remove, node, self.options)
        if rule is not None:
            return rule

        return self.default_rule

    def for_each(self, fn):
        for i in range(len(self.array)):
            fn(self.array[i], i)


def _find_rule(rules, node, options):
    for rule in rules:
        if _filter_value(rule, node, options):
            return rule
    return None


def _filter_value(rule, node, options):
    filter_ = rule["filter"]
    name = node_name(node).lower()

    if isinstance(filter_, str):
        return filter_ == name
    if isinstance(filter_, (list, tuple)):
        return name in filter_
    if callable(filter_):
        return bool(filter_(node, options))
    raise TypeError("`filter` needs to be a string, array, or function")

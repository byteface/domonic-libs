# Adapter that lets domonic use this htmlparser2 port as a parser backend.

from __future__ import annotations

import re
import sys
from typing import Any

from domonic import dom
from domonic import domonic as domonic_class
from domonic.ext._rawdom import (
    HTML_NAMESPACE,
    _append_child_raw,
    _create_comment_raw,
    _create_element_raw,
    _create_fragment_raw,
    _create_text_raw,
    _namespace_for_tag,
    _set_attribute_raw,
)

from .domhandler import DomHandler
from .parser import Parser


PARSER_NAMES = {"htmlparser2", "html-parser2", "html_parser2"}
_installed = False
_prefer_auto = False
_original_parseString = None
_original_set_default_parser = None


class _RawDomHandler:
    def __init__(self, options=None):
        self.options = dict(options or {})
        self.with_start_indices = bool(self.options.get("withStartIndices"))
        self.with_end_indices = bool(self.options.get("withEndIndices"))
        self.root = _create_fragment_raw()
        self.stack = [self.root]
        self.child_stack = [[]]
        self.namespace_stack = [HTML_NAMESPACE]
        self.parser = None

    def onparserinit(self, parser):
        self.parser = parser

    @property
    def current(self):
        return self.stack[-1]

    def onopentag(self, name, attribs, isImplied=False):
        current_namespace = self.namespace_stack[-1]
        current = self.stack[-1]
        if current_namespace == HTML_NAMESPACE and name not in ("svg", "math"):
            namespace_uri = HTML_NAMESPACE
        else:
            parent_tag = getattr(current, "tagName", "")
            parent_encoding = ""
            if isinstance(current, dom.Element):
                parent_encoding = current.getAttribute("encoding") or ""
            namespace_uri = _namespace_for_tag(name, current_namespace, parent_tag, parent_encoding)
        element = _create_element_raw(name, namespace_uri)
        for attr_name, value in (attribs or {}).items():
            _set_attribute_raw(element, attr_name, value)
        if self.with_start_indices and self.parser:
            element.startIndex = self.parser.startIndex
        if self.with_end_indices and self.parser:
            element.endIndex = self.parser.endIndex
        _append_child_raw(current, element, self.child_stack[-1])
        self.stack.append(element)
        self.child_stack.append([])
        self.namespace_stack.append(namespace_uri)

    def onclosetag(self, name=None, isImplied=False):
        if len(self.stack) <= 1:
            return
        element = self.stack.pop()
        children = self.child_stack.pop()
        self.namespace_stack.pop()
        element.__dict__["args"] = tuple(children)
        if self.with_end_indices and self.parser:
            element.endIndex = self.parser.endIndex

    def ontext(self, data):
        if data:
            _append_child_raw(self.stack[-1], _create_text_raw(data), self.child_stack[-1])

    def oncomment(self, data):
        _append_child_raw(self.stack[-1], _create_comment_raw(data), self.child_stack[-1])

    def oncommentend(self):
        pass

    def oncdatastart(self):
        pass

    def oncdataend(self):
        pass

    def onprocessinginstruction(self, name, data):
        node = _create_comment_raw(data)
        node.name = name
        _append_child_raw(self.stack[-1], node, self.child_stack[-1])

    def onend(self):
        for index, node in enumerate(self.stack):
            node.__dict__["args"] = tuple(self.child_stack[index])


def _looks_like_full_html_document(source: str) -> bool:
    probe = source.lstrip().lower()
    return probe.startswith("<!doctype html") or probe.startswith("<html") or "<html" in probe[:512]


def _doctype_from_source(source: str):
    match = re.match(r"^\s*<!doctype\s+([a-zA-Z][^\s>]*)[^>]*>", source, re.I)
    if match is None:
        return None
    return dom.DocumentType(match.group(1).lower(), "", "")


def _upgrade_custom_elements(page):
    if "domonic.window" not in sys.modules:
        return page
    try:
        from domonic.window import window as domonic_window

        registry = domonic_window.customElements
        if getattr(registry, "store", None):
            registry.upgrade(page)
    except Exception:
        return page
    return page


def _ensure_owner_document(page):
    if not isinstance(page, dom.Node) or isinstance(page, dom.Document):
        return page
    if isinstance(page.ownerDocument, dom.Document):
        return page
    owner_document = dom.HTMLDocument()
    for current in dom._iter_dom_nodes(page):
        current._ownerDocument = owner_document
    return page


def parse(source: Any, return_root: bool = True, **kwargs: Any):
    source = "" if source is None else str(source)
    handler_cls = DomHandler if kwargs.pop("domhandler", False) else _RawDomHandler
    handler = handler_cls(kwargs or None)
    Parser(handler, kwargs or None).end(source)
    document = handler.root
    children = getattr(document, "args", ()) or ()
    probe = source.lstrip().lower()
    doctype = _doctype_from_source(source) if probe.startswith("<!doctype") else None

    if probe.startswith("<!doctype html") or probe.startswith("<html") or "<html" in probe[:512]:
        html_root = next((node for node in children if getattr(node, "tagName", "").lower() == "html"), None)
        if html_root is not None:
            if doctype is not None:
                html_root.doctype = doctype
            html_root.parentNode = None
            return _upgrade_custom_elements(_ensure_owner_document(html_root))

    if return_root and len(children) == 1:
        child = children[0]
        if isinstance(child, dom.Node):
            child.parentNode = None
        return _upgrade_custom_elements(_ensure_owner_document(child))

    return _upgrade_custom_elements(_ensure_owner_document(document))


def install(prefer_auto: bool = False):
    """Patch domonic so ``domonic.parseString(..., parser="htmlparser2")`` works.

    ``domonic.parseString`` currently keeps its parser table local to the
    function, so third-party parsers cannot append to it directly. This wrapper
    acts like one extra explicit parser and can optionally be tried first for
    ``parser="auto"``.
    """

    global _installed, _original_parseString, _original_set_default_parser, _prefer_auto
    _prefer_auto = prefer_auto
    if _installed:
        return domonic_class

    _original_parseString = domonic_class.parseString
    _original_set_default_parser = domonic_class.set_default_parser

    def set_default_parser(parser_name: str):
        normalized = (parser_name or "auto").lower()
        if normalized in PARSER_NAMES:
            domonic_class.DEFAULT_PARSER = "htmlparser2"
            return
        return _original_set_default_parser(parser_name)

    def parseString(string, parser=None, debug: bool = False):
        parser_name = (parser or domonic_class.DEFAULT_PARSER or "auto").lower()
        if parser_name in PARSER_NAMES or (parser_name == "auto" and _prefer_auto):
            try:
                page = parse(string, return_root=True)
                domonic_class.parseString_active_parser = "htmlparser2"
                return page
            except Exception:
                if parser_name != "auto":
                    raise
                if debug:
                    print("parseString: auto skipped htmlparser2")
        return _original_parseString(string, parser=parser, debug=debug)

    domonic_class.parseString = staticmethod(parseString)
    domonic_class.set_default_parser = staticmethod(set_default_parser)
    _installed = True
    return domonic_class


def uninstall():
    global _installed
    if not _installed:
        return domonic_class
    domonic_class.parseString = _original_parseString
    domonic_class.set_default_parser = _original_set_default_parser
    _installed = False
    return domonic_class

# Ported from fb55/domhandler (BSD-2-Clause-ish ecosystem dependency shape), backed by domonic.

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from domonic.dom import DocumentFragment, Element, Text
from domonic.html import comment


html_tags = import_module("domonic.html")
_custom_elements = {}


class ElementType:
    Text = "text"
    Comment = "comment"
    Directive = "directive"
    Tag = "tag"
    Script = "script"
    Style = "style"
    CDATA = "cdata"
    Root = "root"


@dataclass
class DomHandlerOptions:
    withStartIndices: bool = False
    withEndIndices: bool = False
    xmlMode: bool = False


class DomHandler:
    def __init__(self, callback=None, options=None, elementCallback=None):
        if callable(options) and elementCallback is None:
            elementCallback = options
            options = None
        if isinstance(callback, dict) and options is None:
            options = callback
            callback = None
        self.callback = callback
        self.options = dict(options or {})
        self.elementCallback = elementCallback
        self.root = DocumentFragment()
        self.root.type = ElementType.Root
        self.root.parent = None
        self.root.prev = None
        self.root.next = None
        self.root.startIndex = None
        self.root.endIndex = None
        self.dom = self.root.args
        self.tagStack = [self.root]
        self.lastNode = None
        self.parser = None
        self.done = False

    def onparserinit(self, parser):
        self.parser = parser

    def onreset(self):
        self.root = DocumentFragment()
        self.root.type = ElementType.Root
        self.root.parent = None
        self.root.prev = None
        self.root.next = None
        self.root.startIndex = None
        self.root.endIndex = None
        self.dom = self.root.args
        self.tagStack = [self.root]
        self.lastNode = None
        self.done = False
        self.parser = None

    def onend(self):
        if self.done:
            return
        self.done = True
        self.parser = None
        if self.callback:
            self.callback(None, self.dom)

    def onerror(self, error):
        if self.callback:
            self.callback(error)
        else:
            raise error

    def onopentag(self, name, attribs, isImplied=False):
        node = self._create_element(name, attribs)
        self._append(node)
        self.tagStack.append(node)

    def onclosetag(self, name=None, isImplied=False):
        self.lastNode = None
        if len(self.tagStack) > 1:
            elem = self.tagStack.pop()
            if self.options.get("withEndIndices") and self.parser:
                elem.endIndex = self.parser.endIndex
            if self.elementCallback:
                self.elementCallback(elem)

    def ontext(self, data):
        if data == "":
            return
        if self.lastNode is not None and getattr(self.lastNode, "type", None) == ElementType.Text:
            self.lastNode.nodeValue = f"{getattr(self.lastNode, 'nodeValue', '')}{data}"
            if self.options.get("withEndIndices") and self.parser:
                self.lastNode.endIndex = self.parser.endIndex
            return
        node = Text(data)
        node.type = ElementType.Text
        node.data = data
        self._append(node)
        self.lastNode = node

    def oncomment(self, data):
        if self.lastNode is not None and getattr(self.lastNode, "type", None) == ElementType.Comment:
            self.lastNode.args = (f"{self.lastNode.args[0]}{data}",)
            self.lastNode.data = self.lastNode.args[0]
            return
        node = comment(data)
        node.type = ElementType.Comment
        node.data = data
        self._append(node)
        self.lastNode = node

    def oncommentend(self):
        self.lastNode = None

    def oncdatastart(self):
        text = Text("")
        text.type = ElementType.Text
        text.data = ""
        node = self._custom_element("cdata")()
        node.type = ElementType.CDATA
        self._append(node)
        self.tagStack.append(node)
        self._append(text)
        self.lastNode = text

    def oncdataend(self):
        self.lastNode = None
        if len(self.tagStack) > 1 and getattr(self.tagStack[-1], "type", None) == ElementType.CDATA:
            self.tagStack.pop()

    def onprocessinginstruction(self, name, data):
        node = comment(data)
        node.name = name
        node.type = ElementType.Directive
        node.data = data
        self._append(node)

    def _append(self, node):
        parent = self.tagStack[-1]
        children = list(getattr(parent, "args", ()) or ())
        previousSibling = children[-1] if children else None
        if self.options.get("withStartIndices") and self.parser:
            node.startIndex = self.parser.startIndex
        elif not hasattr(node, "startIndex"):
            node.startIndex = None
        if self.options.get("withEndIndices") and self.parser:
            node.endIndex = self.parser.endIndex
        elif not hasattr(node, "endIndex"):
            node.endIndex = None
        if hasattr(parent, "appendChild"):
            parent.appendChild(node)
        else:
            parent.args = tuple([*(getattr(parent, "args", ()) or ()), node])
        if previousSibling is not None:
            node.prev = previousSibling
            previousSibling.next = node
        else:
            node.prev = None
        node.next = None
        try:
            node.parentNode = parent
        except Exception:
            pass
        node.parent = parent
        self.lastNode = None

    def _create_element(self, name, attribs):
        kwargs = {f"_{key.replace('-', '_')}": value for key, value in (attribs or {}).items()}
        cls = getattr(html_tags, name, None)
        if cls is None:
            cls = self._custom_element(name)
        node = cls(**kwargs)
        node.type = ElementType.Script if name == "script" else ElementType.Style if name == "style" else ElementType.Tag
        node.attribs = dict(attribs or {})
        node.parent = None
        node.prev = None
        node.next = None
        node.startIndex = None
        node.endIndex = None
        return node

    def _custom_element(self, name):
        cls = _custom_elements.get(name)
        if cls is None:
            cls = type(name, (Element,), {"name": name})
            _custom_elements[name] = cls
        return cls


DefaultHandler = DomHandler

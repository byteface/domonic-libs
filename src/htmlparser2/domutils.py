# Ported-shape domutils subset for htmlparser2's public helpers, backed by domonic nodes.

from __future__ import annotations

from .domhandler import ElementType


def _children(node):
    if isinstance(node, (list, tuple)):
        return list(node)
    return list(getattr(node, "children", None) or getattr(node, "args", None) or getattr(node, "childNodes", None) or [])


def _set_children(parent, children):
    parent.args = tuple(children)
    for index, child in enumerate(children):
        child.parent = parent
        try:
            child.parentNode = parent
        except Exception:
            pass
        child.prev = children[index - 1] if index else None
        child.next = children[index + 1] if index + 1 < len(children) else None


def _tag(node):
    return (getattr(node, "name", "") or getattr(node, "tagName", "") or getattr(node, "nodeName", "") or "").lower()


def _type(node):
    if isinstance(node, str):
        return ElementType.Text
    return getattr(node, "type", None) or (ElementType.Text if getattr(node, "nodeType", None) == 3 else None)


def _attribs(node):
    attribs = getattr(node, "attribs", None)
    if attribs is not None:
        return attribs
    return {
        (key[1:] if key.startswith("_") else key).replace("_", "-"): value
        for key, value in (getattr(node, "kwargs", None) or {}).items()
    }


def isTag(node):
    return _type(node) in (ElementType.Tag, ElementType.Script, ElementType.Style) or getattr(node, "nodeType", None) == 1


def isCDATA(node):
    return _type(node) == ElementType.CDATA


def isText(node):
    return isinstance(node, str) or _type(node) == ElementType.Text or getattr(node, "nodeType", None) == 3


def isComment(node):
    return _type(node) == ElementType.Comment or getattr(node, "nodeType", None) == 8


def isDirective(node):
    return _type(node) == ElementType.Directive


def isDocument(node):
    return _type(node) == ElementType.Root or getattr(node, "nodeType", None) == 9


def hasChildren(node):
    return bool(_children(node)) or hasattr(node, "args") or hasattr(node, "children") or hasattr(node, "childNodes")


def getChildren(element):
    return _children(element)


def getParent(element):
    return getattr(element, "parent", None) or getattr(element, "parentNode", None)


def getSiblings(element):
    parent = getParent(element)
    if parent is not None:
        return getChildren(parent)
    siblings = [element]
    prev = getattr(element, "prev", None)
    next_ = getattr(element, "next", None)
    while prev is not None:
        siblings.insert(0, prev)
        prev = getattr(prev, "prev", None)
    while next_ is not None:
        siblings.append(next_)
        next_ = getattr(next_, "next", None)
    return siblings


def getAttributeValue(element, name):
    return _attribs(element).get(name)


def hasAttrib(element, name):
    return name in _attribs(element) and _attribs(element).get(name) is not None


def getName(element):
    return getattr(element, "name", None) or _tag(element)


def nextElementSibling(element):
    next_ = getattr(element, "next", None)
    while next_ is not None and not isTag(next_):
        next_ = getattr(next_, "next", None)
    return next_


def prevElementSibling(element):
    prev = getattr(element, "prev", None)
    while prev is not None and not isTag(prev):
        prev = getattr(prev, "prev", None)
    return prev


def filter(test, node, recurse=True, limit=float("inf")):
    return find(test, node if isinstance(node, (list, tuple)) else [node], recurse, limit)


def find(test, nodes, recurse=True, limit=float("inf")):
    result = []
    stack = [list(nodes) if isinstance(nodes, (list, tuple)) else [nodes]]
    indexes = [0]
    while True:
        if indexes[0] >= len(stack[0]):
            if len(stack) == 1:
                return result
            stack.pop(0)
            indexes.pop(0)
            continue
        element = stack[0][indexes[0]]
        indexes[0] += 1
        if test(element):
            result.append(element)
            limit -= 1
            if limit <= 0:
                return result
        children = _children(element)
        if recurse and children:
            indexes.insert(0, 0)
            stack.insert(0, children)


def findAll(test, nodes):
    return [node for node in find(lambda node: isTag(node) and test(node), nodes, True, float("inf"))]


def findOne(test, nodes, recurse=True):
    searchedNodes = list(nodes) if isinstance(nodes, (list, tuple)) else [nodes]
    for node in searchedNodes:
        if isTag(node) and test(node):
            return node
        children = _children(node)
        if recurse and children:
            found = findOne(test, children, True)
            if found is not None:
                return found
    return None


def existsOne(test, nodes):
    searchedNodes = list(nodes) if isinstance(nodes, (list, tuple)) else [nodes]
    return any((isTag(node) and test(node)) or (_children(node) and existsOne(test, _children(node))) for node in searchedNodes)


def _compile_check(options):
    checks = []
    for key, value in (options or {}).items():
        if key == "tag_name":
            if callable(value):
                checks.append(lambda node, value=value: isTag(node) and value(getName(node)))
            elif value == "*":
                checks.append(isTag)
            else:
                checks.append(lambda node, value=value: isTag(node) and getName(node) == value)
        elif key == "tag_type":
            checks.append(lambda node, value=value: _type(node) == value or (callable(value) and value(_type(node))))
        elif key == "tag_contains":
            checks.append(lambda node, value=value: isText(node) and (value(textContent(node)) if callable(value) else textContent(node) == value))
        elif callable(value):
            checks.append(lambda node, key=key, value=value: isTag(node) and value(_attribs(node).get(key)))
        else:
            checks.append(lambda node, key=key, value=value: isTag(node) and _attribs(node).get(key) == value)
    if not checks:
        return None
    return lambda node: any(check(node) for check in checks)


def testElement(options, node):
    test = _compile_check(options)
    return test(node) if test else True


def getElements(options, nodes, recurse=True, limit=float("inf")):
    test = _compile_check(options)
    return filter(test, nodes, recurse, limit) if test else []


def getElementById(id_, nodes, recurse=True):
    test = (lambda node: callable(id_) and id_(_attribs(node).get("id"))) if callable(id_) else (lambda node: _attribs(node).get("id") == id_)
    return findOne(test, nodes, recurse)


def getElementsByTagName(name, nodes, recurse=True, limit=float("inf")):
    test = (lambda node: name(getName(node))) if callable(name) else (lambda node: _tag(node) == str(name).lower())
    return filter(lambda node: isTag(node) and test(node), nodes, recurse, limit)


def getElementsByClassName(className, nodes, recurse=True, limit=float("inf")):
    def test(node):
        value = _attribs(node).get("class", "")
        return className(value) if callable(className) else className in value.split()

    return filter(lambda node: isTag(node) and test(node), nodes, recurse, limit)


def getElementsByTagType(type_, nodes, recurse=True, limit=float("inf")):
    return filter(lambda node: _type(node) == type_ or (callable(type_) and type_(_type(node))), nodes, recurse, limit)


def getOuterHTML(node, options=None):
    if isinstance(node, (list, tuple)):
        return "".join(getOuterHTML(child, options) for child in node)
    return str(node)


def getInnerHTML(node, options=None):
    return "".join(getOuterHTML(child, options) for child in _children(node))


def getText(node):
    if isinstance(node, (list, tuple)):
        return "".join(getText(child) for child in node)
    if isTag(node):
        return "\n" if getName(node) == "br" else getText(_children(node))
    if isCDATA(node):
        return getText(_children(node))
    if isText(node):
        return str(node) if isinstance(node, str) else str(getattr(node, "data", None) or getattr(node, "nodeValue", "") or node)
    return ""


def textContent(node):
    if isinstance(node, (list, tuple)):
        return "".join(textContent(child) for child in node)
    if isText(node):
        return str(node) if isinstance(node, str) else str(getattr(node, "data", None) or getattr(node, "nodeValue", "") or node)
    if hasChildren(node) and not isComment(node):
        return textContent(_children(node))
    return ""


def innerText(node):
    if isinstance(node, (list, tuple)):
        return "".join(innerText(child) for child in node)
    if hasChildren(node) and (_type(node) == ElementType.Tag or isCDATA(node)):
        return innerText(_children(node))
    if isText(node):
        return str(node) if isinstance(node, str) else str(getattr(node, "data", None) or getattr(node, "nodeValue", "") or node)
    return ""


def removeElement(element):
    prev = getattr(element, "prev", None)
    next_ = getattr(element, "next", None)
    parent = getParent(element)
    if prev is not None:
        prev.next = next_
    if next_ is not None:
        next_.prev = prev
    if parent is not None:
        children = _children(parent)
        if element in children:
            children.pop(len(children) - 1 - children[::-1].index(element))
            _set_children(parent, children)
    element.next = None
    element.prev = None
    element.parent = None


def replaceElement(element, replacement):
    parent = getParent(element)
    children = _children(parent) if parent is not None else []
    if parent is not None and element in children:
        children[children.index(element)] = replacement
        _set_children(parent, children)
    replacement.prev = getattr(element, "prev", None)
    replacement.next = getattr(element, "next", None)
    replacement.parent = parent
    if replacement.prev is not None:
        replacement.prev.next = replacement
    if replacement.next is not None:
        replacement.next.prev = replacement
    element.parent = None
    element.prev = None
    element.next = None


def appendChild(parent, child):
    removeElement(child)
    _set_children(parent, [*_children(parent), child])


def prependChild(parent, child):
    removeElement(child)
    _set_children(parent, [child, *_children(parent)])


def append(element, next_):
    removeElement(next_)
    parent = getParent(element)
    if parent is None:
        next_.prev = element
        next_.next = getattr(element, "next", None)
        element.next = next_
        next_.parent = None
        return
    children = _children(parent)
    children.insert(children.index(element) + 1, next_)
    _set_children(parent, children)


def prepend(element, previous):
    removeElement(previous)
    parent = getParent(element)
    if parent is None:
        previous.next = element
        previous.prev = getattr(element, "prev", None)
        element.prev = previous
        previous.parent = None
        return
    children = _children(parent)
    children.insert(children.index(element), previous)
    _set_children(parent, children)


class DomUtils:
    append = staticmethod(append)
    appendChild = staticmethod(appendChild)
    existsOne = staticmethod(existsOne)
    filter = staticmethod(filter)
    find = staticmethod(find)
    findAll = staticmethod(findAll)
    findOne = staticmethod(findOne)
    getAttributeValue = staticmethod(getAttributeValue)
    getChildren = staticmethod(getChildren)
    getElementById = staticmethod(getElementById)
    getElements = staticmethod(getElements)
    getElementsByClassName = staticmethod(getElementsByClassName)
    getElementsByTagName = staticmethod(getElementsByTagName)
    getElementsByTagType = staticmethod(getElementsByTagType)
    getInnerHTML = staticmethod(getInnerHTML)
    getName = staticmethod(getName)
    getOuterHTML = staticmethod(getOuterHTML)
    getParent = staticmethod(getParent)
    getSiblings = staticmethod(getSiblings)
    getText = staticmethod(getText)
    hasAttrib = staticmethod(hasAttrib)
    hasChildren = staticmethod(hasChildren)
    innerText = staticmethod(innerText)
    isCDATA = staticmethod(isCDATA)
    isComment = staticmethod(isComment)
    isDirective = staticmethod(isDirective)
    isDocument = staticmethod(isDocument)
    isTag = staticmethod(isTag)
    isText = staticmethod(isText)
    nextElementSibling = staticmethod(nextElementSibling)
    prepend = staticmethod(prepend)
    prependChild = staticmethod(prependChild)
    prevElementSibling = staticmethod(prevElementSibling)
    removeElement = staticmethod(removeElement)
    replaceElement = staticmethod(replaceElement)
    testElement = staticmethod(testElement)
    textContent = staticmethod(textContent)

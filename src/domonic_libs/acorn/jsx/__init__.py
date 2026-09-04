# Ported from acornjs/acorn-jsx (MIT), tag acorn-jsx@5.3.2. Mirrors index.js.
# Preserve the upstream licence when redistributing.
"""JSX support for the acorn port -- a ``Parser`` subclass that adds the JSX
grammar (elements, fragments, attributes, expression containers, namespaced /
member names, entities).

    from domonic_libs.acorn.jsx import parse_jsx
    parse_jsx("<div className='x'>{items}</div>", {"ecmaVersion": 2022}).to_dict()
"""

from __future__ import annotations

from domonic.javascript import RegExp, String

from ..identifier import isIdentifierChar, isIdentifierStart
from ..parser import Parser
from ..tokencontext import TokContext
from ..tokencontext import types as _tokContexts
from ..tokentype import TokenType
from ..tokentype import tt
from ..whitespace import isNewLine
from .xhtml import XHTML_ENTITIES

_hexNumber = RegExp(r"^[\da-fA-F]+$")
_decimalNumber = RegExp(r"^\d+$")

# -- JSX token contexts -----------------------------------------------------

tc_oTag = TokContext("<tag", False)
tc_cTag = TokContext("</tag", False)
tc_expr = TokContext("<tag>...</tag>", True, True)

# -- JSX token types ------------------------------------------------------

jsxName = TokenType("jsxName")
jsxText = TokenType("jsxText", {"beforeExpr": True})
jsxTagStart = TokenType("jsxTagStart", {"startsExpr": True})
jsxTagEnd = TokenType("jsxTagEnd")


def _upd_tagStart(self, prevType):
    self.context.append(tc_expr)
    self.context.append(tc_oTag)
    self.exprAllowed = False


def _upd_tagEnd(self, prevType):
    out = self.context.pop()
    if (out is tc_oTag and prevType is tt.slash) or out is tc_cTag:
        self.context.pop()
        self.exprAllowed = self.curContext() is tc_expr
    else:
        self.exprAllowed = True


jsxTagStart.updateContext = _upd_tagStart
jsxTagEnd.updateContext = _upd_tagEnd


def _qualifiedName(obj):
    if not obj:
        return obj
    if obj.type == "JSXIdentifier":
        return obj.name
    if obj.type == "JSXNamespacedName":
        return obj.namespace.name + ":" + obj.name.name
    if obj.type == "JSXMemberExpression":
        return _qualifiedName(obj.object) + "." + _qualifiedName(obj.property)


class JSXParser(Parser):
    def __init__(self, options, inp, startPos=None, allow_namespaces=True, allow_namespaced_objects=False):
        self._jsx_allowNamespaces = allow_namespaces
        self._jsx_allowNamespacedObjects = allow_namespaced_objects
        super().__init__(options, inp, startPos)

    # -- token readers --------------------------------------------------

    def jsx_readToken(self):
        out = ""
        chunkStart = self.pos
        while True:
            if self.pos >= self.input.length:
                self.raise_(self.start, "Unterminated JSX contents")
            ch = self.input.charCodeAt(self.pos)
            if ch == 60 or ch == 123:  # '<' '{'
                if self.pos == self.start:
                    if ch == 60 and self.exprAllowed:
                        self.pos += 1
                        return self.finishToken(jsxTagStart)
                    return self.getTokenFromCode(ch)
                out += str(self.input.slice(chunkStart, self.pos))
                return self.finishToken(jsxText, out)
            if ch == 38:  # '&'
                out += str(self.input.slice(chunkStart, self.pos))
                out += self.jsx_readEntity()
                chunkStart = self.pos
            elif ch == 62 or ch == 125:  # '>' '}'
                self.raise_(self.pos, "Unexpected token `" + self.input[self.pos] + "`. Did you mean `"
                            + ("&gt;" if ch == 62 else "&rbrace;") + '` or `{"' + self.input[self.pos] + '"}`?')
            else:
                if isNewLine(ch):
                    out += str(self.input.slice(chunkStart, self.pos))
                    out += self.jsx_readNewLine(True)
                    chunkStart = self.pos
                else:
                    self.pos += 1

    def jsx_readNewLine(self, normalizeCRLF):
        ch = self.input.charCodeAt(self.pos)
        self.pos += 1
        if ch == 13 and self.input.charCodeAt(self.pos) == 10:
            self.pos += 1
            out = "\n" if normalizeCRLF else "\r\n"
        else:
            out = String.fromCharCode(ch)
        if self.options["locations"]:
            self.curLine += 1
            self.lineStart = self.pos
        return out

    def jsx_readString(self, quote):
        out = ""
        self.pos += 1
        chunkStart = self.pos
        while True:
            if self.pos >= self.input.length:
                self.raise_(self.start, "Unterminated string constant")
            ch = self.input.charCodeAt(self.pos)
            if ch == quote:
                break
            if ch == 38:  # '&'
                out += str(self.input.slice(chunkStart, self.pos))
                out += self.jsx_readEntity()
                chunkStart = self.pos
            elif isNewLine(ch):
                out += str(self.input.slice(chunkStart, self.pos))
                out += self.jsx_readNewLine(False)
                chunkStart = self.pos
            else:
                self.pos += 1
        out += str(self.input.slice(chunkStart, self.pos))
        self.pos += 1
        return self.finishToken(tt.string, out)

    def jsx_readEntity(self):
        s = ""
        count = 0
        entity = None
        ch = self.input[self.pos]
        if ch != "&":
            self.raise_(self.pos, "Entity must start with an ampersand")
        self.pos += 1
        startPos = self.pos
        while self.pos < self.input.length and count < 10:
            count += 1
            ch = self.input[self.pos]
            self.pos += 1
            if ch == ";":
                if s[:1] == "#":
                    if s[1:2] == "x":
                        s = s[2:]
                        if bool(_hexNumber.test(s)):
                            entity = String.fromCharCode(int(s, 16))
                    else:
                        s = s[1:]
                        if bool(_decimalNumber.test(s)):
                            entity = String.fromCharCode(int(s, 10))
                else:
                    entity = XHTML_ENTITIES.get(s)
                break
            s += ch
        if not entity:
            self.pos = startPos
            return "&"
        return entity

    def jsx_readWord(self):
        start = self.pos
        while True:
            self.pos += 1
            ch = self.input.charCodeAt(self.pos)
            if not (isIdentifierChar(ch) or ch == 45):  # '-'
                break
        return self.finishToken(jsxName, str(self.input.slice(start, self.pos)))

    # -- element / attribute grammar ----------------------------------

    def jsx_parseIdentifier(self):
        node = self.startNode()
        if self.type is jsxName:
            node.name = self.value
        elif self.type.keyword:
            node.name = self.type.keyword
        else:
            self.unexpected()
        self.next()
        return self.finishNode(node, "JSXIdentifier")

    def jsx_parseNamespacedName(self):
        startPos, startLoc = self.start, self.startLoc
        name = self.jsx_parseIdentifier()
        if not self._jsx_allowNamespaces or not self.eat(tt.colon):
            return name
        node = self.startNodeAt(startPos, startLoc)
        node.namespace = name
        node.name = self.jsx_parseIdentifier()
        return self.finishNode(node, "JSXNamespacedName")

    def jsx_parseElementName(self):
        if self.type is jsxTagEnd:
            return ""
        startPos, startLoc = self.start, self.startLoc
        node = self.jsx_parseNamespacedName()
        if self.type is tt.dot and node.type == "JSXNamespacedName" and not self._jsx_allowNamespacedObjects:
            self.unexpected()
        while self.eat(tt.dot):
            newNode = self.startNodeAt(startPos, startLoc)
            newNode.object = node
            newNode.property = self.jsx_parseIdentifier()
            node = self.finishNode(newNode, "JSXMemberExpression")
        return node

    def jsx_parseAttributeValue(self):
        if self.type is tt.braceL:
            node = self.jsx_parseExpressionContainer()
            if node.expression.type == "JSXEmptyExpression":
                self.raise_(node.start, "JSX attributes must only be assigned a non-empty expression")
            return node
        if self.type is jsxTagStart or self.type is tt.string:
            return self.parseExprAtom()
        self.raise_(self.start, "JSX value should be either an expression or a quoted JSX text")

    def jsx_parseEmptyExpression(self):
        node = self.startNodeAt(self.lastTokEnd, self.lastTokEndLoc)
        return self.finishNodeAt(node, "JSXEmptyExpression", self.start, self.startLoc)

    def jsx_parseExpressionContainer(self):
        node = self.startNode()
        self.next()
        node.expression = self.jsx_parseEmptyExpression() if self.type is tt.braceR else self.parseExpression()
        self.expect(tt.braceR)
        return self.finishNode(node, "JSXExpressionContainer")

    def jsx_parseAttribute(self):
        node = self.startNode()
        if self.eat(tt.braceL):
            self.expect(tt.ellipsis)
            node.argument = self.parseMaybeAssign()
            self.expect(tt.braceR)
            return self.finishNode(node, "JSXSpreadAttribute")
        node.name = self.jsx_parseNamespacedName()
        node.value = self.jsx_parseAttributeValue() if self.eat(tt.eq) else None
        return self.finishNode(node, "JSXAttribute")

    def jsx_parseOpeningElementAt(self, startPos, startLoc):
        node = self.startNodeAt(startPos, startLoc)
        node.attributes = []
        nodeName = self.jsx_parseElementName()
        if nodeName:
            node.name = nodeName
        while self.type is not tt.slash and self.type is not jsxTagEnd:
            node.attributes.append(self.jsx_parseAttribute())
        node.selfClosing = self.eat(tt.slash)
        self.expect(jsxTagEnd)
        return self.finishNode(node, "JSXOpeningElement" if nodeName else "JSXOpeningFragment")

    def jsx_parseClosingElementAt(self, startPos, startLoc):
        node = self.startNodeAt(startPos, startLoc)
        nodeName = self.jsx_parseElementName()
        if nodeName:
            node.name = nodeName
        self.expect(jsxTagEnd)
        return self.finishNode(node, "JSXClosingElement" if nodeName else "JSXClosingFragment")

    def jsx_parseElementAt(self, startPos, startLoc):
        node = self.startNodeAt(startPos, startLoc)
        children = []
        openingElement = self.jsx_parseOpeningElementAt(startPos, startLoc)
        closingElement = None
        if not openingElement.selfClosing:
            while True:
                if self.type is jsxTagStart:
                    startPos, startLoc = self.start, self.startLoc
                    self.next()
                    if self.eat(tt.slash):
                        closingElement = self.jsx_parseClosingElementAt(startPos, startLoc)
                        break
                    children.append(self.jsx_parseElementAt(startPos, startLoc))
                elif self.type is jsxText:
                    children.append(self.parseExprAtom())
                elif self.type is tt.braceL:
                    children.append(self.jsx_parseExpressionContainer())
                else:
                    self.unexpected()
            if _qualifiedName(closingElement.name if hasattr(closingElement, "name") else None) \
                    != _qualifiedName(openingElement.name if hasattr(openingElement, "name") else None):
                self.raise_(closingElement.start,
                            "Expected corresponding JSX closing tag for <"
                            + str(_qualifiedName(getattr(openingElement, "name", None))) + ">")
        fragmentOrElement = "Element" if getattr(openingElement, "name", None) else "Fragment"
        setattr(node, "opening" + fragmentOrElement, openingElement)
        setattr(node, "closing" + fragmentOrElement, closingElement)
        node.children = children
        if self.type is tt.relational and self.value == "<":
            self.raise_(self.start, "Adjacent JSX elements must be wrapped in an enclosing tag")
        return self.finishNode(node, "JSX" + fragmentOrElement)

    def jsx_parseText(self):
        node = self.parseLiteral(self.value)
        node.type = "JSXText"
        return node

    def jsx_parseElement(self):
        startPos, startLoc = self.start, self.startLoc
        self.next()
        return self.jsx_parseElementAt(startPos, startLoc)

    # -- overrides ----------------------------------------------------

    def parseExprAtom(self, refDestructuringErrors=None, forInit=False, forNew=False):
        if self.type is jsxText:
            return self.jsx_parseText()
        if self.type is jsxTagStart:
            return self.jsx_parseElement()
        return super().parseExprAtom(refDestructuringErrors, forInit, forNew)

    def readToken(self, code):
        context = self.curContext()
        if context is tc_expr:
            return self.jsx_readToken()
        if context is tc_oTag or context is tc_cTag:
            if isIdentifierStart(code):
                return self.jsx_readWord()
            if code == 62:  # '>'
                self.pos += 1
                return self.finishToken(jsxTagEnd)
            if (code == 34 or code == 39) and context is tc_oTag:
                return self.jsx_readString(code)
        if code == 60 and self.exprAllowed and self.input.charCodeAt(self.pos + 1) != 33:
            self.pos += 1
            return self.finishToken(jsxTagStart)
        return super().readToken(code)

    def updateContext(self, prevType):
        if self.type is tt.braceL:
            curContext = self.curContext()
            if curContext is tc_oTag:
                self.context.append(_tokContexts["b_expr"])
            elif curContext is tc_expr:
                self.context.append(_tokContexts["b_tmpl"])
            else:
                super().updateContext(prevType)
            self.exprAllowed = True
        elif self.type is tt.slash and prevType is jsxTagStart:
            del self.context[-2:]
            self.context.append(tc_cTag)
            self.exprAllowed = False
        else:
            super().updateContext(prevType)


def parse_jsx(src, options=None, allow_namespaces=True, allow_namespaced_objects=False):
    p = JSXParser(options, src, None, allow_namespaces, allow_namespaced_objects)
    return p.parse()

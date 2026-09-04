# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/lval.js.
"""Turning expression atoms into assignable patterns, and the ``checkLVal*``
family that validates and records bindings."""

from __future__ import annotations

from .scopeflags import BIND_LEXICAL, BIND_NONE, BIND_OUTSIDE
from .tokentype import tt
from .util import hasOwn


class LValMixin:
    def toAssignable(self, node, isBinding, refDestructuringErrors=None):
        if self.options["ecmaVersion"] >= 6 and node:
            t = node.type
            if t == "Identifier":
                if self.inAsync and node.name == "await":
                    self.raise_(node.start, "Cannot use 'await' as identifier inside an async function")
            elif t in ("ObjectPattern", "ArrayPattern", "AssignmentPattern", "RestElement"):
                pass
            elif t == "ObjectExpression":
                node.type = "ObjectPattern"
                if refDestructuringErrors:
                    self.checkPatternErrors(refDestructuringErrors, True)
                for prop in node.properties:
                    self.toAssignable(prop, isBinding)
                    if prop.type == "RestElement" and prop.argument.type in ("ArrayPattern", "ObjectPattern"):
                        self.raise_(prop.argument.start, "Unexpected token")
            elif t == "Property":
                if node.kind != "init":
                    self.raise_(node.key.start, "Object pattern can't contain getter or setter")
                self.toAssignable(node.value, isBinding)
            elif t == "ArrayExpression":
                node.type = "ArrayPattern"
                if refDestructuringErrors:
                    self.checkPatternErrors(refDestructuringErrors, True)
                self.toAssignableList(node.elements, isBinding)
            elif t == "SpreadElement":
                node.type = "RestElement"
                self.toAssignable(node.argument, isBinding)
                if node.argument.type == "AssignmentPattern":
                    self.raise_(node.argument.start, "Rest elements cannot have a default value")
            elif t == "AssignmentExpression":
                if node.operator != "=":
                    self.raise_(node.left.end, "Only '=' operator can be used for specifying default value.")
                node.type = "AssignmentPattern"
                if hasattr(node, "operator"):
                    del node.operator
                self.toAssignable(node.left, isBinding)
            elif t == "ParenthesizedExpression":
                self.toAssignable(node.expression, isBinding, refDestructuringErrors)
            elif t == "ChainExpression":
                self.raiseRecoverable(node.start, "Optional chaining cannot appear in left-hand side")
            elif t == "MemberExpression":
                if not isBinding:
                    pass
                else:
                    self.raise_(node.start, "Assigning to rvalue")
            else:
                self.raise_(node.start, "Assigning to rvalue")
        elif refDestructuringErrors:
            self.checkPatternErrors(refDestructuringErrors, True)
        return node

    def toAssignableList(self, exprList, isBinding):
        end = len(exprList)
        for i in range(end):
            elt = exprList[i]
            if elt:
                self.toAssignable(elt, isBinding)
        if end:
            last = exprList[end - 1]
            if (self.options["ecmaVersion"] == 6 and isBinding and last
                    and last.type == "RestElement" and last.argument.type != "Identifier"):
                self.unexpected(last.argument.start)
        return exprList

    def parseSpread(self, refDestructuringErrors):
        node = self.startNode()
        self.next()
        node.argument = self.parseMaybeAssign(False, refDestructuringErrors)
        return self.finishNode(node, "SpreadElement")

    def parseRestBinding(self):
        node = self.startNode()
        self.next()
        if self.options["ecmaVersion"] == 6 and self.type is not tt.name:
            self.unexpected()
        node.argument = self.parseBindingAtom()
        return self.finishNode(node, "RestElement")

    def parseBindingAtom(self):
        if self.options["ecmaVersion"] >= 6:
            if self.type is tt.bracketL:
                node = self.startNode()
                self.next()
                node.elements = self.parseBindingList(tt.bracketR, True, True)
                return self.finishNode(node, "ArrayPattern")
            if self.type is tt.braceL:
                return self.parseObj(True)
        return self.parseIdent()

    def parseBindingList(self, close, allowEmpty, allowTrailingComma, allowModifiers=False):
        elts = []
        first = True
        while not self.eat(close):
            if first:
                first = False
            else:
                self.expect(tt.comma)
            if allowEmpty and self.type is tt.comma:
                elts.append(None)
            elif allowTrailingComma and self.afterTrailingComma(close):
                break
            elif self.type is tt.ellipsis:
                rest = self.parseRestBinding()
                self.parseBindingListItem(rest)
                elts.append(rest)
                if self.type is tt.comma:
                    self.raiseRecoverable(self.start, "Comma is not permitted after the rest element")
                self.expect(close)
                break
            else:
                elts.append(self.parseAssignableListItem(allowModifiers))
        return elts

    def parseAssignableListItem(self, allowModifiers):
        elem = self.parseMaybeDefault(self.start, self.startLoc)
        self.parseBindingListItem(elem)
        return elem

    def parseBindingListItem(self, param):
        return param

    def parseMaybeDefault(self, startPos, startLoc, left=None):
        left = left or self.parseBindingAtom()
        if self.options["ecmaVersion"] < 6 or not self.eat(tt.eq):
            return left
        node = self.startNodeAt(startPos, startLoc)
        node.left = left
        node.right = self.parseMaybeAssign()
        return self.finishNode(node, "AssignmentPattern")

    def checkLValSimple(self, expr, bindingType=BIND_NONE, checkClashes=None):
        isBind = bindingType != BIND_NONE
        t = expr.type
        if t == "Identifier":
            if self.strict and bool(self.reservedWordsStrictBind.test(expr.name)):
                self.raiseRecoverable(expr.start, ("Binding " if isBind else "Assigning to ") + expr.name + " in strict mode")
            if isBind:
                if bindingType == BIND_LEXICAL and expr.name == "let":
                    self.raiseRecoverable(expr.start, "let is disallowed as a lexically bound name")
                if checkClashes is not None:
                    if hasOwn(checkClashes, expr.name):
                        self.raiseRecoverable(expr.start, "Argument name clash")
                    checkClashes[expr.name] = True
                if bindingType != BIND_OUTSIDE:
                    self.declareName(expr.name, bindingType, expr.start)
        elif t == "ChainExpression":
            self.raiseRecoverable(expr.start, "Optional chaining cannot appear in left-hand side")
        elif t == "MemberExpression":
            if isBind:
                self.raiseRecoverable(expr.start, "Binding member expression")
        elif t == "ParenthesizedExpression":
            if isBind:
                self.raiseRecoverable(expr.start, "Binding parenthesized expression")
            return self.checkLValSimple(expr.expression, bindingType, checkClashes)
        else:
            self.raise_(expr.start, ("Binding" if isBind else "Assigning to") + " rvalue")

    def checkLValPattern(self, expr, bindingType=BIND_NONE, checkClashes=None):
        t = expr.type
        if t == "ObjectPattern":
            for prop in expr.properties:
                self.checkLValInnerPattern(prop, bindingType, checkClashes)
        elif t == "ArrayPattern":
            for elem in expr.elements:
                if elem:
                    self.checkLValInnerPattern(elem, bindingType, checkClashes)
        else:
            self.checkLValSimple(expr, bindingType, checkClashes)

    def checkLValInnerPattern(self, expr, bindingType=BIND_NONE, checkClashes=None):
        t = expr.type
        if t == "Property":
            self.checkLValInnerPattern(expr.value, bindingType, checkClashes)
        elif t == "AssignmentPattern":
            self.checkLValPattern(expr.left, bindingType, checkClashes)
        elif t == "RestElement":
            self.checkLValPattern(expr.argument, bindingType, checkClashes)
        else:
            self.checkLValPattern(expr, bindingType, checkClashes)

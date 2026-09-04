# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/parseutil.js.
"""Parser plumbing: token eating, ASI, contextual keywords, and the
``DestructuringErrors`` deferred-error record."""

from __future__ import annotations

from .tokentype import tt
from .whitespace import lineBreak

UNDEF = object()  # stand-in for JS `undefined` where `null`/`None` is meaningful


class DestructuringErrors:
    def __init__(self):
        self.shorthandAssign = -1
        self.trailingComma = -1
        self.parenthesizedAssign = -1
        self.parenthesizedBind = -1
        self.doubleProto = -1


class ParseUtilMixin:
    def eat(self, type):
        if self.type is type:
            self.next()
            return True
        return False

    def isContextual(self, name):
        return self.type is tt.name and self.value == name and not self.containsEsc

    def eatContextual(self, name):
        if not self.isContextual(name):
            return False
        self.next()
        return True

    def expectContextual(self, name):
        if not self.eatContextual(name):
            self.unexpected()

    def catchStackOverflow(self, f):
        try:
            return f()
        except RecursionError:
            self.raise_(self.start, "Not enough stack space to parse input")

    def canInsertSemicolon(self):
        return (self.type is tt.eof or self.type is tt.braceR
                or bool(lineBreak.test(self.input.slice(self.lastTokEnd, self.start))))

    def insertSemicolon(self):
        return bool(self.canInsertSemicolon())

    def semicolon(self):
        if not self.eat(tt.semi) and not self.insertSemicolon():
            self.unexpected()

    def afterTrailingComma(self, tokType, notNext=False):
        if self.type is tokType:
            if not notNext:
                self.next()
            return True
        return False

    def expect(self, type):
        if not self.eat(type):
            self.unexpected()

    # unexpected() is defined on the tokenizer (raise_ + "Unexpected token").

    def checkPatternErrors(self, refDestructuringErrors, isAssign):
        if not refDestructuringErrors:
            return
        if refDestructuringErrors.trailingComma > -1:
            self.raiseRecoverable(refDestructuringErrors.trailingComma, "Comma is not permitted after the rest element")
        parens = refDestructuringErrors.parenthesizedAssign if isAssign else refDestructuringErrors.parenthesizedBind
        if parens > -1:
            self.raiseRecoverable(parens, "Assigning to rvalue" if isAssign else "Parenthesized pattern")

    def checkExpressionErrors(self, refDestructuringErrors, andThrow=False):
        if not refDestructuringErrors:
            return False
        shorthandAssign = refDestructuringErrors.shorthandAssign
        doubleProto = refDestructuringErrors.doubleProto
        if not andThrow:
            return shorthandAssign >= 0 or doubleProto >= 0
        if shorthandAssign >= 0:
            self.raise_(shorthandAssign, "Shorthand property assignments are valid only in destructuring patterns")
        if doubleProto >= 0:
            self.raiseRecoverable(doubleProto, "Redefinition of __proto__ property")
        return False

    def checkYieldAwaitInDefaultParams(self):
        if self.yieldPos and (not self.awaitPos or self.yieldPos < self.awaitPos):
            self.raise_(self.yieldPos, "Yield expression cannot be a default value")
        if self.awaitPos:
            self.raise_(self.awaitPos, "Await expression cannot be a default value")

    def isSimpleAssignTarget(self, expr):
        if expr.type == "ParenthesizedExpression":
            return self.isSimpleAssignTarget(expr.expression)
        return expr.type == "Identifier" or expr.type == "MemberExpression"

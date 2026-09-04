# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors the parser half of
# src/state.js plus the src/index.js entry points.
"""``Parser`` -- the full recursive-descent parser, assembled from the tokenizer
and the statement / expression / lval / scope / node mixins."""

from __future__ import annotations

from .expression import ExpressionMixin
from .lval import LValMixin
from .node import NodeMixin
from .options import getOptions
from .parseutil import ParseUtilMixin
from .scope import ScopeMixin
from .scopeflags import (
    SCOPE_ARROW,
    SCOPE_ASYNC,
    SCOPE_CLASS_FIELD_INIT,
    SCOPE_CLASS_STATIC_BLOCK,
    SCOPE_DIRECT_SUPER,
    SCOPE_FUNCTION,
    SCOPE_GENERATOR,
    SCOPE_SUPER,
    SCOPE_SWITCH,
    SCOPE_TOP,
)
from .state import Tokenizer
from .statement import StatementMixin


class Parser(
    Tokenizer,
    NodeMixin,
    ScopeMixin,
    ParseUtilMixin,
    LValMixin,
    ExpressionMixin,
    StatementMixin,
):
    def __init__(self, options, inp, startPos=None):
        options = getOptions(options)
        Tokenizer.__init__(self, options, inp, startPos)

        self.potentialArrowInForAwait = False
        self.yieldPos = self.awaitPos = self.awaitIdentPos = 0
        self.labels = []
        self.undefinedExports = {}
        self.scopeStack = []
        self.enterScope(
            SCOPE_FUNCTION if self.options["sourceType"] == "commonjs" else SCOPE_TOP
        )
        self.regexpState = None
        self.privateNameStack = []

    # -- scope-derived predicates (src/state.js getters) -----------------

    @property
    def inFunction(self):
        return (self.currentVarScope().flags & SCOPE_FUNCTION) > 0

    @property
    def inGenerator(self):
        return (self.currentVarScope().flags & SCOPE_GENERATOR) > 0

    @property
    def inAsync(self):
        return (self.currentVarScope().flags & SCOPE_ASYNC) > 0

    @property
    def canAwait(self):
        for i in range(len(self.scopeStack) - 1, -1, -1):
            flags = self.scopeStack[i].flags
            if flags & (SCOPE_CLASS_STATIC_BLOCK | SCOPE_CLASS_FIELD_INIT):
                return False
            if flags & SCOPE_FUNCTION:
                return (flags & SCOPE_ASYNC) > 0
        return (self.inModule and self.options["ecmaVersion"] >= 13) or bool(self.options["allowAwaitOutsideFunction"])

    @property
    def allowReturn(self):
        if self.inFunction:
            return True
        if self.options["allowReturnOutsideFunction"] and (self.currentVarScope().flags & SCOPE_TOP):
            return True
        return False

    @property
    def allowSuper(self):
        flags = self.currentThisScope().flags
        return (flags & SCOPE_SUPER) > 0 or bool(self.options["allowSuperOutsideMethod"])

    @property
    def allowDirectSuper(self):
        return (self.currentThisScope().flags & SCOPE_DIRECT_SUPER) > 0

    @property
    def treatFunctionsAsVar(self):
        return self.treatFunctionsAsVarInScope(self.currentScope())

    @property
    def allowNewDotTarget(self):
        for i in range(len(self.scopeStack) - 1, -1, -1):
            flags = self.scopeStack[i].flags
            if (flags & (SCOPE_CLASS_STATIC_BLOCK | SCOPE_CLASS_FIELD_INIT)
                    or ((flags & SCOPE_FUNCTION) and not (flags & SCOPE_ARROW))):
                return True
        return False

    @property
    def allowUsing(self):
        flags = self.currentScope().flags
        if flags & SCOPE_SWITCH:
            return False
        if not self.inModule and flags & SCOPE_TOP:
            return False
        return True

    @property
    def inClassStaticBlock(self):
        return (self.currentVarScope().flags & SCOPE_CLASS_STATIC_BLOCK) > 0

    # -- entry points (src/state.js + src/index.js) ---------------------

    def parse(self):
        node = self.options["program"] or self.startNode()
        self.nextToken()
        return self.catchStackOverflow(lambda: self.parseTopLevel(node))

    @classmethod
    def do_parse(cls, inp, options=None):
        return cls(options, inp).parse()

    @classmethod
    def parseExpressionAt(cls, inp, pos, options=None):
        p = cls(options, inp, pos)
        p.nextToken()
        return p.parseExpression()


def parse(inp, options=None):
    """Parse ``inp`` and return an ESTree ``Node`` (call ``.to_dict()`` for a
    plain nested-dict form)."""
    return Parser.do_parse(inp, options)


def parse_expression_at(inp, pos, options=None):
    return Parser.parseExpressionAt(inp, pos, options)

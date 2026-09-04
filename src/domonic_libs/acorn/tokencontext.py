# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/tokencontext.js.
# Preserve the upstream licence when redistributing.
"""The token-context stack -- acorn's heuristic for deciding whether a ``/``
starts a regex or a division. Ported as a mixin on the tokenizer plus the
per-token ``updateContext`` callbacks."""

from __future__ import annotations

from .tokentype import tt
from .whitespace import lineBreak


class TokContext:
    def __init__(self, token, isExpr=False, preserveSpace=False, override=None, generator=False):
        self.token = token
        self.isExpr = bool(isExpr)
        self.preserveSpace = bool(preserveSpace)
        self.override = override
        self.generator = bool(generator)


types = {
    "b_stat": TokContext("{", False),
    "b_expr": TokContext("{", True),
    "b_tmpl": TokContext("${", False),
    "p_stat": TokContext("(", False),
    "p_expr": TokContext("(", True),
    "q_tmpl": TokContext("`", True, True, lambda p: p.tryReadTemplateToken()),
    "f_stat": TokContext("function", False),
    "f_expr": TokContext("function", True),
    "f_expr_gen": TokContext("function", True, False, None, True),
    "f_gen": TokContext("function", False, False, None, True),
}
_ct = types


class TokenContextMixin:
    def initialContext(self):
        return [_ct["b_stat"]]

    def curContext(self):
        return self.context[-1]

    def braceIsBlock(self, prevType):
        parent = self.curContext()
        if parent is _ct["f_expr"] or parent is _ct["f_stat"]:
            return True
        if prevType is tt.colon and (parent is _ct["b_stat"] or parent is _ct["b_expr"]):
            return not parent.isExpr
        if prevType is tt._return or (prevType is tt.name and self.exprAllowed):
            return bool(lineBreak.test(self.input.slice(self.lastTokEnd, self.start)))
        if prevType in (tt._else, tt.semi, tt.eof, tt.parenR, tt.arrow):
            return True
        if prevType is tt.braceL:
            return parent is _ct["b_stat"]
        if prevType in (tt._var, tt._const, tt.name):
            return False
        return not self.exprAllowed

    def inGeneratorContext(self):
        for i in range(len(self.context) - 1, 0, -1):
            context = self.context[i]
            if context.token == "function":
                return context.generator
        return False

    def updateContext(self, prevType):
        typ = self.type
        if typ.keyword and prevType is tt.dot:
            self.exprAllowed = False
            return
        update = typ.updateContext
        if update:
            update(self, prevType)
        else:
            self.exprAllowed = typ.beforeExpr

    def overrideContext(self, tokenCtx):
        if self.curContext() is not tokenCtx:
            self.context[-1] = tokenCtx


# -- token-specific context update code (attached to the TokenType objects) --

def _upd_parenR_braceR(self, prevType):
    if len(self.context) == 1:
        self.exprAllowed = True
        return
    out = self.context.pop()
    if out is _ct["b_stat"] and self.curContext().token == "function":
        out = self.context.pop()
    self.exprAllowed = not out.isExpr


tt.parenR.updateContext = tt.braceR.updateContext = _upd_parenR_braceR


def _upd_braceL(self, prevType):
    self.context.append(_ct["b_stat"] if self.braceIsBlock(prevType) else _ct["b_expr"])
    self.exprAllowed = True


tt.braceL.updateContext = _upd_braceL


def _upd_dollarBraceL(self, prevType):
    self.context.append(_ct["b_tmpl"])
    self.exprAllowed = True


tt.dollarBraceL.updateContext = _upd_dollarBraceL


def _upd_parenL(self, prevType):
    statementParens = prevType in (tt._if, tt._for, tt._with, tt._while)
    self.context.append(_ct["p_stat"] if statementParens else _ct["p_expr"])
    self.exprAllowed = True


tt.parenL.updateContext = _upd_parenL


def _upd_incDec(self, prevType):
    pass  # exprAllowed stays unchanged


tt.incDec.updateContext = _upd_incDec


def _upd_function_class(self, prevType):
    if (prevType.beforeExpr and prevType is not tt._else
            and not (prevType is tt.semi and self.curContext() is not _ct["p_stat"])
            and not (prevType is tt._return and lineBreak.test(self.input.slice(self.lastTokEnd, self.start)))
            and not ((prevType is tt.colon or prevType is tt.braceL) and self.curContext() is _ct["b_stat"])):
        self.context.append(_ct["f_expr"])
    else:
        self.context.append(_ct["f_stat"])
    self.exprAllowed = False


tt._function.updateContext = tt._class.updateContext = _upd_function_class


def _upd_colon(self, prevType):
    if self.curContext().token == "function":
        self.context.pop()
    self.exprAllowed = True


tt.colon.updateContext = _upd_colon


def _upd_backQuote(self, prevType):
    if self.curContext() is _ct["q_tmpl"]:
        self.context.pop()
    else:
        self.context.append(_ct["q_tmpl"])
    self.exprAllowed = False


tt.backQuote.updateContext = _upd_backQuote


def _upd_star(self, prevType):
    if prevType is tt._function:
        index = len(self.context) - 1
        if self.context[index] is _ct["f_expr"]:
            self.context[index] = _ct["f_expr_gen"]
        else:
            self.context[index] = _ct["f_gen"]
    self.exprAllowed = True


tt.star.updateContext = _upd_star


def _upd_name(self, prevType):
    allowed = False
    if self.options["ecmaVersion"] >= 6 and prevType is not tt.dot:
        if (self.value == "of" and not self.exprAllowed) or (self.value == "yield" and self.inGeneratorContext()):
            allowed = True
    self.exprAllowed = allowed


tt.name.updateContext = _upd_name

# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/tokentype.js.
# Preserve the upstream licence when redistributing.
"""Token type table.

Each ``TokenType`` carries the flags the parser reads off a token
(``beforeExpr`` for regex-vs-divide disambiguation, ``startsExpr``, ``binop``
precedence, ...). ``updateContext`` starts as ``None`` and is filled in by
``tokencontext``.
"""

from __future__ import annotations


class TokenType:
    def __init__(self, label, conf=None):
        conf = conf or {}
        self.label = label
        self.keyword = conf.get("keyword")
        self.beforeExpr = bool(conf.get("beforeExpr"))
        self.startsExpr = bool(conf.get("startsExpr"))
        self.isLoop = bool(conf.get("isLoop"))
        self.isAssign = bool(conf.get("isAssign"))
        self.prefix = bool(conf.get("prefix"))
        self.postfix = bool(conf.get("postfix"))
        self.binop = conf.get("binop")
        self.updateContext = None

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<TokenType {self.label!r}>"


def _binop(name, prec):
    return TokenType(name, {"beforeExpr": True, "binop": prec})


_beforeExpr = {"beforeExpr": True}
_startsExpr = {"startsExpr": True}

keywords = {}


def _kw(name, options=None):
    options = dict(options or {})
    options["keyword"] = name
    keywords[name] = TokenType(name, options)
    return keywords[name]


types = {
    "num": TokenType("num", _startsExpr),
    "regexp": TokenType("regexp", _startsExpr),
    "string": TokenType("string", _startsExpr),
    "name": TokenType("name", _startsExpr),
    "privateId": TokenType("privateId", _startsExpr),
    "eof": TokenType("eof"),

    "bracketL": TokenType("[", {"beforeExpr": True, "startsExpr": True}),
    "bracketR": TokenType("]"),
    "braceL": TokenType("{", {"beforeExpr": True, "startsExpr": True}),
    "braceR": TokenType("}"),
    "parenL": TokenType("(", {"beforeExpr": True, "startsExpr": True}),
    "parenR": TokenType(")"),
    "comma": TokenType(",", _beforeExpr),
    "semi": TokenType(";", _beforeExpr),
    "colon": TokenType(":", _beforeExpr),
    "dot": TokenType("."),
    "question": TokenType("?", _beforeExpr),
    "questionDot": TokenType("?."),
    "arrow": TokenType("=>", _beforeExpr),
    "template": TokenType("template"),
    "invalidTemplate": TokenType("invalidTemplate"),
    "ellipsis": TokenType("...", _beforeExpr),
    "backQuote": TokenType("`", _startsExpr),
    "dollarBraceL": TokenType("${", {"beforeExpr": True, "startsExpr": True}),

    "eq": TokenType("=", {"beforeExpr": True, "isAssign": True}),
    "assign": TokenType("_=", {"beforeExpr": True, "isAssign": True}),
    "incDec": TokenType("++/--", {"prefix": True, "postfix": True, "startsExpr": True}),
    "prefix": TokenType("!/~", {"beforeExpr": True, "prefix": True, "startsExpr": True}),
    "logicalOR": _binop("||", 1),
    "logicalAND": _binop("&&", 2),
    "bitwiseOR": _binop("|", 3),
    "bitwiseXOR": _binop("^", 4),
    "bitwiseAND": _binop("&", 5),
    "equality": _binop("==/!=/===/!==", 6),
    "relational": _binop("</>/<=/>=", 7),
    "bitShift": _binop("<</>>/>>>", 8),
    "plusMin": TokenType("+/-", {"beforeExpr": True, "binop": 9, "prefix": True, "startsExpr": True}),
    "modulo": _binop("%", 10),
    "star": _binop("*", 10),
    "slash": _binop("/", 10),
    "starstar": TokenType("**", {"beforeExpr": True}),
    "coalesce": _binop("??", 1),

    "_break": _kw("break"),
    "_case": _kw("case", _beforeExpr),
    "_catch": _kw("catch"),
    "_continue": _kw("continue"),
    "_debugger": _kw("debugger"),
    "_default": _kw("default", _beforeExpr),
    "_do": _kw("do", {"isLoop": True, "beforeExpr": True}),
    "_else": _kw("else", _beforeExpr),
    "_finally": _kw("finally"),
    "_for": _kw("for", {"isLoop": True}),
    "_function": _kw("function", _startsExpr),
    "_if": _kw("if"),
    "_return": _kw("return", _beforeExpr),
    "_switch": _kw("switch"),
    "_throw": _kw("throw", _beforeExpr),
    "_try": _kw("try"),
    "_var": _kw("var"),
    "_const": _kw("const"),
    "_while": _kw("while", {"isLoop": True}),
    "_with": _kw("with"),
    "_new": _kw("new", {"beforeExpr": True, "startsExpr": True}),
    "_this": _kw("this", _startsExpr),
    "_super": _kw("super", _startsExpr),
    "_class": _kw("class", _startsExpr),
    "_extends": _kw("extends", _beforeExpr),
    "_export": _kw("export"),
    "_import": _kw("import", _startsExpr),
    "_null": _kw("null", _startsExpr),
    "_true": _kw("true", _startsExpr),
    "_false": _kw("false", _startsExpr),
    "_in": _kw("in", {"beforeExpr": True, "binop": 7}),
    "_instanceof": _kw("instanceof", {"beforeExpr": True, "binop": 7}),
    "_typeof": _kw("typeof", {"beforeExpr": True, "prefix": True, "startsExpr": True}),
    "_void": _kw("void", {"beforeExpr": True, "prefix": True, "startsExpr": True}),
    "_delete": _kw("delete", {"beforeExpr": True, "prefix": True, "startsExpr": True}),
}


class _TT:
    """Attribute access over the ``types`` dict, so ports can write ``tt.parenR``."""

    def __getattr__(self, name):
        try:
            return types[name]
        except KeyError:
            raise AttributeError(name)


tt = _TT()

# Ported in spirit from escodegen (BSD-2) -- an ESTree -> JavaScript printer.
"""Turn an ESTree AST back into JavaScript source.

The third leg of the acorn port: ``parse`` reads JS -> AST, ``interpret`` runs
an AST, and ``generate`` writes an AST back out as source.

    from domonic_libs.acorn import parse, generate

    generate(parse("const f = x => x*2"))          # 'const f = x => x * 2;'
    generate(parse(src), minify=True)               # whitespace-stripped
    minify("big.js")                                # read a file, return minified text

``generate`` accepts either the ``Node`` tree ``parse`` returns or the plain
nested dicts from ``Node.to_dict()``. It round-trips: ``parse(generate(ast))``
produces an equivalent tree.
"""

from __future__ import annotations

import re

__all__ = ["generate", "minify"]

# -- node access (works on both Node objects and plain dicts) ----------


def _t(node):
    return node["type"] if isinstance(node, dict) else getattr(node, "type", None)


def _g(node, key, default=None):
    if isinstance(node, dict):
        return node.get(key, default)
    return getattr(node, key, default)


# -- operator precedence ----------------------------------------------

_BINARY_PREC = {
    "||": 4, "??": 4,
    "&&": 5,
    "|": 6, "^": 7, "&": 8,
    "==": 9, "!=": 9, "===": 9, "!==": 9,
    "<": 10, ">": 10, "<=": 10, ">=": 10, "in": 10, "instanceof": 10,
    "<<": 11, ">>": 11, ">>>": 11,
    "+": 12, "-": 12,
    "*": 13, "/": 13, "%": 13,
    "**": 14,
}
_P_SEQUENCE = 0
_P_ASSIGN = 1        # assignment / arrow / yield
_P_CONDITIONAL = 2
_P_UNARY = 15
_P_POSTFIX = 16
_P_CALL = 17
_P_PRIMARY = 20

_RIGHT_ASSOC = {"**"}

_IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*$")

_ESC = {
    chr(92): chr(92) + chr(92), chr(10): chr(92) + "n", chr(13): chr(92) + "r", chr(9): chr(92) + "t",
    chr(8): chr(92) + "b", chr(12): chr(92) + "f", chr(11): chr(92) + "v", chr(0): chr(92) + "0",
    chr(0x2028): chr(92) + "u2028", chr(0x2029): chr(92) + "u2029",
}


def _quote(s, prefer='"'):
    other = "'" if prefer == '"' else '"'
    # pick the quote that needs the fewer escapes
    if s.count(prefer) > s.count(other):
        prefer, other = other, prefer
    out = [prefer]
    for ch in s:
        if ch == prefer:
            out.append("\\" + ch)
        elif ch in _ESC:
            out.append(_ESC[ch])
        elif ch < " " and ch not in "\n\r\t":
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    out.append(prefer)
    return "".join(out)


def _num(value, raw):
    # keep the source form when it's already minimal-ish, else repr the float
    if raw is not None and isinstance(raw, str):
        r = raw
        # strip a redundant leading zero: 0.5 -> .5 only in minify (done by caller)
        return r
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e16:
            return str(int(value))
        return repr(value)
    return str(value)


class _Gen:
    def __init__(self, minify=False, indent="  ", quote='"', semi=True):
        self.min = minify
        self.indent_unit = "" if minify else indent
        self.q = quote
        self.semi = semi
        self._depth = 0

    # -- whitespace helpers
    @property
    def nl(self):
        return "" if self.min else "\n"

    @property
    def sp(self):
        return "" if self.min else " "

    def ind(self):
        return "" if self.min else self.indent_unit * self._depth

    def _blk(self, body):
        """A `{ ... }` block from a list of statements."""
        if not body:
            return "{}"
        self._depth += 1
        inner = self.nl.join(self.ind() + self.stmt(s) for s in body)
        self._depth -= 1
        return "{" + self.nl + inner + self.nl + self.ind() + "}"

    # -- entry
    def gen(self, node):
        ty = _t(node)
        if ty == "Program":
            return self.nl.join(self.ind() + self.stmt(s) for s in _g(node, "body", []))
        if ty and ty.endswith(("Statement", "Declaration")) or ty in (
            "VariableDeclarator", "SwitchCase", "CatchClause", "ClassBody",
        ):
            return self.stmt(node)
        return self.expr(node)

    # -- statements ---------------------------------------------------
    def stmt(self, node):
        ty = _t(node)
        m = getattr(self, "_s_" + ty, None)
        if m is None:
            raise ValueError(f"generate: unsupported statement {ty!r}")
        return m(node)

    def _semi(self):
        return ";" if self.semi else ""

    def _s_ExpressionStatement(self, n):
        e = _g(n, "expression")
        s = self.expr(e)
        # an expression statement whose first token is `{`, `function`,
        # `async function`, `class`, or `let [` is read as a block / a
        # declaration instead -- wrap the whole thing (covers an object
        # literal, a bare function/class expression, and an IIFE like
        # `(function(){})()` whose rendered form starts with `function`).
        if s and (s[0] == "{" or s.startswith((
            "function", "async function", "class ", "class{", "let[", "let ["))):
            s = "(" + s + ")"
        return s + self._semi()

    def _s_EmptyStatement(self, n):
        return ";"

    def _s_DebuggerStatement(self, n):
        return "debugger" + self._semi()

    def _s_BlockStatement(self, n):
        return self._blk(_g(n, "body", []))

    def _s_StaticBlock(self, n):
        return "static " + self._blk(_g(n, "body", []))

    def _s_WithStatement(self, n):
        return f"with{self.sp}(" + self.expr(_g(n, "object")) + ")" + self._body(_g(n, "body"))

    def _s_ReturnStatement(self, n):
        a = _g(n, "argument")
        return "return" + ((" " + self.expr(a)) if a is not None else "") + self._semi()

    def _s_ThrowStatement(self, n):
        return "throw " + self.expr(_g(n, "argument")) + self._semi()

    def _s_BreakStatement(self, n):
        lbl = _g(n, "label")
        return "break" + ((" " + _g(lbl, "name")) if lbl else "") + self._semi()

    def _s_ContinueStatement(self, n):
        lbl = _g(n, "label")
        return "continue" + ((" " + _g(lbl, "name")) if lbl else "") + self._semi()

    def _s_LabeledStatement(self, n):
        return _g(_g(n, "label"), "name") + ":" + self.sp + self.stmt(_g(n, "body"))

    def _body(self, node, *, kw=False):
        """The controlled statement of if/for/while/else/do -- an inline block,
        or ``\\n  stmt``. ``kw=True`` means it follows a bare keyword (`else`,
        `do`) and so, when minified onto one line, needs a space before a
        non-`{` statement or the keyword fuses with the next token
        (`elsestmt`)."""
        if _t(node) == "BlockStatement":
            return self.sp + self._blk(_g(node, "body", []))
        self._depth += 1
        s = self.nl + self.ind() + self.stmt(node)
        self._depth -= 1
        if kw and self.min and not s.startswith("{"):
            s = " " + s
        return s

    def _s_IfStatement(self, n):
        out = f"if{self.sp}(" + self.expr(_g(n, "test")) + ")"
        cons = _g(n, "consequent")
        alt = _g(n, "alternate")
        out += self._body(cons)
        if alt is not None:
            sep = self.sp if _t(cons) == "BlockStatement" else (self.nl + self.ind())
            if _t(alt) == "IfStatement":
                out += sep + "else " + self.stmt(alt)
            else:
                out += sep + "else" + self._body(alt, kw=True)
        return out

    def _s_WhileStatement(self, n):
        return f"while{self.sp}(" + self.expr(_g(n, "test")) + ")" + self._body(_g(n, "body"))

    def _s_DoWhileStatement(self, n):
        body = self._body(_g(n, "body"), kw=True)
        tail = f"while{self.sp}(" + self.expr(_g(n, "test")) + ")" + self._semi()
        if _t(_g(n, "body")) == "BlockStatement":
            return "do" + body + self.sp + tail
        # the body statement already carries its own `;` (or ends `}`); just
        # a newline (pretty) or nothing (minified) before `while`
        sep = "" if (self.min or body.rstrip().endswith((";", "}"))) else self.nl + self.ind()
        glue = ";" if (self.min and not body.rstrip().endswith((";", "}"))) else ""
        return "do" + body + glue + sep + tail

    def _for_head(self, node):
        if node is None:
            return ""
        if _t(node) == "VariableDeclaration":
            return self._var(node, semi=False)
        return self.expr(node)

    def _s_ForStatement(self, n):
        head = ";".join((
            self._for_head(_g(n, "init")),
            self.expr(_g(n, "test")) if _g(n, "test") is not None else "",
            self.expr(_g(n, "update")) if _g(n, "update") is not None else "",
        ))
        return f"for{self.sp}(" + head + ")" + self._body(_g(n, "body"))

    def _for_x(self, n, kw, *, awaited=False):
        left = _g(n, "left")
        lstr = self._var(left, semi=False) if _t(left) == "VariableDeclaration" else self.expr(left)
        rprec = _P_ASSIGN if kw == "of" else _P_SEQUENCE
        head = ("for await " if awaited else "for" + self.sp) + "(" + lstr + f" {kw} " + self.expr(_g(n, "right"), rprec) + ")"
        return head + self._body(_g(n, "body"))

    def _s_ForInStatement(self, n):
        return self._for_x(n, "in")

    def _s_ForOfStatement(self, n):
        return self._for_x(n, "of", awaited=bool(_g(n, "await")))

    def _s_SwitchStatement(self, n):
        self._depth += 1
        cases = self.nl.join(self.ind() + self._case(c) for c in _g(n, "cases", []))
        self._depth -= 1
        return (f"switch{self.sp}(" + self.expr(_g(n, "discriminant")) + ")" + self.sp
                + "{" + self.nl + cases + self.nl + self.ind() + "}")

    def _case(self, c):
        test = _g(c, "test")
        head = ("case " + self.expr(test) + ":") if test is not None else "default:"
        body = _g(c, "consequent", [])
        if not body:
            return head
        if len(body) == 1 and _t(body[0]) != "BlockStatement":
            return head + " " + self.stmt(body[0])
        self._depth += 1
        inner = self.nl.join(self.ind() + self.stmt(s) for s in body)
        self._depth -= 1
        return head + self.nl + inner

    def _s_TryStatement(self, n):
        out = "try" + self.sp + self._blk(_g(_g(n, "block"), "body", []))
        h = _g(n, "handler")
        if h is not None:
            param = _g(h, "param")
            pstr = (self.sp + "(" + self.pattern(param) + ")") if param is not None else ""
            out += self.sp + "catch" + pstr + self.sp + self._blk(_g(_g(h, "body"), "body", []))
        f = _g(n, "finalizer")
        if f is not None:
            out += self.sp + "finally" + self.sp + self._blk(_g(f, "body", []))
        return out

    # -- declarations
    def _var(self, n, *, semi=True):
        decls = ("," + self.sp).join(self._declarator(d) for d in _g(n, "declarations", []))
        s = _g(n, "kind", "var") + " " + decls
        return s + (self._semi() if semi else "")

    _s_VariableDeclaration = _var

    def _declarator(self, d):
        idn = self.pattern(_g(d, "id"))
        init = _g(d, "init")
        if init is None:
            return idn
        return idn + self.sp + "=" + self.sp + self.expr(init, _P_ASSIGN)

    def _s_FunctionDeclaration(self, n):
        return self._function(n)

    def _s_ClassDeclaration(self, n):
        return self._class(n)

    # -- modules
    def _s_ImportDeclaration(self, n):
        specs = _g(n, "specifiers", [])
        src = self.expr(_g(n, "source"))
        if not specs:
            return "import " + src + self._semi()
        parts, named = [], []
        for s in specs:
            st = _t(s)
            if st == "ImportDefaultSpecifier":
                parts.append(_g(_g(s, "local"), "name"))
            elif st == "ImportNamespaceSpecifier":
                parts.append("* as " + _g(_g(s, "local"), "name"))
            else:
                imp = _g(s, "imported")
                iname = _g(imp, "name") if _t(imp) == "Identifier" else _quote(_g(imp, "value"), self.q)
                lname = _g(_g(s, "local"), "name")
                named.append(iname if iname == lname else f"{iname} as {lname}")
        if named:
            parts.append("{" + self.sp + ("," + self.sp).join(named) + self.sp + "}")
        return "import " + ("," + self.sp).join(parts) + " from " + src + self._semi()

    def _s_ExportNamedDeclaration(self, n):
        decl = _g(n, "declaration")
        if decl is not None:
            return "export " + self.stmt(decl)
        specs = []
        for s in _g(n, "specifiers", []):
            loc = _g(_g(s, "local"), "name")
            exp = _g(_g(s, "exported"), "name")
            specs.append(loc if loc == exp else f"{loc} as {exp}")
        out = "export " + "{" + self.sp + ("," + self.sp).join(specs) + self.sp + "}"
        src = _g(n, "source")
        if src is not None:
            out += " from " + self.expr(src)
        return out + self._semi()

    def _s_ExportDefaultDeclaration(self, n):
        d = _g(n, "declaration")
        s = self.stmt(d) if _t(d).endswith(("Declaration",)) else self.expr(d) + self._semi()
        return "export default " + s

    def _s_ExportAllDeclaration(self, n):
        exp = _g(n, "exported")
        as_ = (" as " + _g(exp, "name")) if exp is not None else ""
        return "export *" + as_ + " from " + self.expr(_g(n, "source")) + self._semi()

    # -- shared: functions & classes
    def _function(self, n, *, method=False):
        # `method=True` -> just `(params) { body }` -- the caller (`_member`
        # / `_prop`) has already emitted `async` / `*` / `get` / `set` and
        # the key, so emitting them here too would double them (`*name*()`).
        params = "(" + ("," + self.sp).join(self.pattern(p) for p in _g(n, "params", [])) + ")"
        body = self.sp + self._blk(_g(_g(n, "body"), "body", []))
        if method:
            return params + body
        a = "async " if _g(n, "async") else ""
        star = "*" if _g(n, "generator") else ""
        name = _g(n, "id")
        nm = (" " + _g(name, "name")) if name else ""
        return a + "function" + star + nm + params + body

    def _class(self, n):
        name = _g(n, "id")
        nm = (" " + _g(name, "name")) if name else ""
        sc = _g(n, "superClass")
        ext = (" extends " + self.expr(sc, _P_CALL)) if sc is not None else ""
        members = _g(_g(n, "body"), "body", [])
        if not members:
            return "class" + nm + ext + self.sp + "{}"
        self._depth += 1
        inner = self.nl.join(self.ind() + self._member(m) for m in members)
        self._depth -= 1
        return "class" + nm + ext + self.sp + "{" + self.nl + inner + self.nl + self.ind() + "}"

    def _member(self, m):
        ty = _t(m)
        if ty == "StaticBlock":
            return self._s_StaticBlock(m)
        static = "static " if _g(m, "static") else ""
        key = self._key(m)
        if ty == "PropertyDefinition":
            v = _g(m, "value")
            return static + key + ((self.sp + "=" + self.sp + self.expr(v, _P_ASSIGN)) if v is not None else "") + self._semi()
        # MethodDefinition
        kind = _g(m, "kind")
        fn = _g(m, "value")
        prefix = ""
        if kind in ("get", "set"):
            prefix = kind + " "
        if _g(fn, "async"):
            prefix = "async " + prefix
        if _g(fn, "generator"):
            prefix += "*"
        return static + prefix + key + self._function(fn, method=True)

    def _key(self, node):
        if _g(node, "computed"):
            return "[" + self.expr(_g(node, "key"), _P_ASSIGN) + "]"
        k = _g(node, "key")
        if _t(k) == "PrivateIdentifier":
            return "#" + _g(k, "name")
        if _t(k) == "Identifier":
            return _g(k, "name")
        if _t(k) == "Literal":
            val = _g(k, "value")
            # only drop the quotes when minifying -- `{"a": 1}` -> `{a: 1}`
            # is a real size win, but in pretty mode the quoted key is kept
            # so a parse/generate round-trip preserves the exact AST
            if self.min and isinstance(val, str) and _IDENT_RE.match(val):
                return val
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return _num(val, _g(k, "raw"))
            return self._s_Literal_value(k)
        return self.expr(k)

    # -- expressions -----------------------------------------------
    def expr(self, node, ctx_prec=_P_SEQUENCE):
        if node is None:
            return ""
        ty = _t(node)
        m = getattr(self, "_e_" + ty, None)
        if m is None:
            raise ValueError(f"generate: unsupported expression {ty!r}")
        s, prec = m(node)
        if prec < ctx_prec:
            return "(" + s + ")"
        return s

    def _e_Identifier(self, n):
        return _g(n, "name"), _P_PRIMARY

    def _e_PrivateIdentifier(self, n):
        return "#" + _g(n, "name"), _P_PRIMARY

    def _e_Super(self, n):
        return "super", _P_PRIMARY

    def _e_ThisExpression(self, n):
        return "this", _P_PRIMARY

    def _e_MetaProperty(self, n):
        return _g(_g(n, "meta"), "name") + "." + _g(_g(n, "property"), "name"), _P_PRIMARY

    def _s_Literal_value(self, n):
        return self._e_Literal(n)[0]

    def _e_Literal(self, n):
        # regex
        rx = _g(n, "regex")
        if rx is not None:
            return "/" + _g(rx, "pattern") + "/" + _g(rx, "flags", ""), _P_PRIMARY
        raw = _g(n, "raw")
        val = _g(n, "value")
        if raw is not None and isinstance(raw, str) and (raw.endswith("n") or raw[:1] in "/\"'`0123456789." or raw in ("true", "false", "null")):
            # bigint / already-good numeric or string raw -- but re-quote strings for safety
            if isinstance(val, str) and not raw.endswith("n"):
                return _quote(val, self.q), _P_PRIMARY
            return raw, _P_PRIMARY
        if val is None:
            return "null", _P_PRIMARY
        if isinstance(val, bool):
            return ("true" if val else "false"), _P_PRIMARY
        if isinstance(val, str):
            return _quote(val, self.q), _P_PRIMARY
        return _num(val, raw), (_P_PRIMARY if not (isinstance(val, (int, float)) and val < 0) else _P_UNARY)

    def _e_TemplateLiteral(self, n):
        quasis = _g(n, "quasis", [])
        exprs = _g(n, "expressions", [])
        out = ["`"]
        for i, q in enumerate(quasis):
            out.append(_g(_g(q, "value"), "raw", ""))
            if i < len(exprs):
                out.append("${" + self.expr(exprs[i]) + "}")
        out.append("`")
        return "".join(out), _P_PRIMARY

    def _e_TaggedTemplateExpression(self, n):
        return self.expr(_g(n, "tag"), _P_CALL) + self._e_TemplateLiteral(_g(n, "quasi"))[0], _P_CALL

    def _e_ArrayExpression(self, n):
        els = _g(n, "elements", [])
        parts = []
        for e in els:
            if e is None:
                parts.append("")
            elif _t(e) == "SpreadElement":
                parts.append("..." + self.expr(_g(e, "argument"), _P_ASSIGN))
            else:
                parts.append(self.expr(e, _P_ASSIGN))
        inner = ("," + self.sp).join(parts)
        if parts and parts[-1] == "":
            inner += ","
        return "[" + inner + "]", _P_PRIMARY

    def _e_ObjectExpression(self, n):
        props = _g(n, "properties", [])
        if not props:
            return "{}", _P_PRIMARY
        parts = [self._prop(p) for p in props]
        if self.min:
            return "{" + ",".join(parts) + "}", _P_PRIMARY
        self._depth += 1
        inner = (",\n").join(self.ind() + p for p in parts)
        self._depth -= 1
        return "{\n" + inner + "\n" + self.ind() + "}", _P_PRIMARY

    def _prop(self, p):
        if _t(p) == "SpreadElement":
            return "..." + self.expr(_g(p, "argument"), _P_ASSIGN)
        kind = _g(p, "kind", "init")
        val = _g(p, "value")
        if kind in ("get", "set"):
            return kind + " " + self._key(p) + self._function(val, method=True)
        if _g(val, "type") in ("FunctionExpression",) and _g(p, "method"):
            pre = ("async " if _g(val, "async") else "") + ("*" if _g(val, "generator") else "")
            return pre + self._key(p) + self._function(val, method=True)
        key = self._key(p)
        if _g(p, "shorthand"):
            return key
        return key + ":" + self.sp + self.expr(val, _P_ASSIGN)

    def _e_FunctionExpression(self, n):
        return self._function(n), _P_PRIMARY

    def _e_ClassExpression(self, n):
        return self._class(n), _P_PRIMARY

    def _e_ArrowFunctionExpression(self, n):
        a = "async " if _g(n, "async") else ""
        params = _g(n, "params", [])
        if len(params) == 1 and _t(params[0]) == "Identifier":
            head = _g(params[0], "name")
        else:
            head = "(" + ("," + self.sp).join(self.pattern(p) for p in params) + ")"
        body = _g(n, "body")
        if _g(n, "expression") or _t(body) != "BlockStatement":
            bs = self.expr(body, _P_ASSIGN)
            if bs and bs[0] == "{":
                bs = "(" + bs + ")"
            return a + head + self.sp + "=>" + self.sp + bs, _P_ASSIGN
        return a + head + self.sp + "=>" + self.sp + self._blk(_g(body, "body", [])), _P_ASSIGN

    def _e_UnaryExpression(self, n):
        op = _g(n, "operator")
        argn = _g(n, "argument")
        arg = self.expr(argn, _P_UNARY)
        # `-1 ** 2` is a *syntax error* in JS -- an unparenthesised unary
        # can't be the left of `**` -- so `Unary(-, Binary(**, ...))` has to
        # print as `-(1 ** 2)` (precedence already parenthesises `**` under
        # a unary context, so this is usually a no-op belt-and-braces).
        if (_t(argn) == "BinaryExpression" and _g(argn, "operator") == "**"
                and not arg.startswith("(")):
            arg = "(" + arg + ")"
        sep = " " if op[-1].isalpha() else ""
        # `-` on `-x` / `--x`, or `+` on `+x` / `++x`, must not run together
        # into `--` / `++` (a decrement/increment) -- a space keeps them apart
        if not sep and op in ("-", "+") and arg[:1] == op:
            sep = " "
        return op + sep + arg, _P_UNARY

    def _e_UpdateExpression(self, n):
        op = _g(n, "operator")
        arg = self.expr(_g(n, "argument"), _P_UNARY)
        return (op + arg, _P_UNARY) if _g(n, "prefix") else (arg + op, _P_POSTFIX)

    def _e_BinaryExpression(self, n):
        op = _g(n, "operator")
        prec = _BINARY_PREC.get(op, 10)
        right_assoc = op in _RIGHT_ASSOC
        ln = _g(n, "left")
        left = self.expr(ln, prec + (1 if right_assoc else 0))
        right = self.expr(_g(n, "right"), prec + (0 if right_assoc else 1))
        # same rule the other way round: `(-1) ** 2` -- the left of `**`
        # can't be a bare unary/await/prefix-update
        if op == "**" and _t(ln) in ("UnaryExpression", "AwaitExpression") or (
                op == "**" and _t(ln) == "UpdateExpression" and _g(ln, "prefix")):
            left = "(" + left + ")"
        spaced = op[0].isalpha() or not self.min
        j = f" {op} " if spaced else op
        # `a + +b` / `a - -b` / `a + ++b` must not fuse into `a++b` / `a---b`
        if not spaced and op in ("+", "-") and (left.endswith(op) or right.startswith(op)):
            j = op + " "
        return left + j + right, prec

    _e_LogicalExpression = _e_BinaryExpression

    def _e_AssignmentExpression(self, n):
        left = self.pattern(_g(n, "left")) if _t(_g(n, "left")) in ("ObjectPattern", "ArrayPattern") else self.expr(_g(n, "left"), _P_CALL)
        right = self.expr(_g(n, "right"), _P_ASSIGN)
        return left + self.sp + _g(n, "operator") + self.sp + right, _P_ASSIGN

    def _e_ConditionalExpression(self, n):
        t = self.expr(_g(n, "test"), _P_CONDITIONAL + 1)
        c = self.expr(_g(n, "consequent"), _P_ASSIGN)
        a = self.expr(_g(n, "alternate"), _P_ASSIGN)
        return f"{t}{self.sp}?{self.sp}{c}{self.sp}:{self.sp}{a}", _P_CONDITIONAL

    def _e_SequenceExpression(self, n):
        return ("," + self.sp).join(self.expr(e, _P_ASSIGN) for e in _g(n, "expressions", [])), _P_SEQUENCE

    def _e_CallExpression(self, n):
        callee = self.expr(_g(n, "callee"), _P_CALL)
        opt = "?." if _g(n, "optional") else ""
        args = ("," + self.sp).join(self._arg(a) for a in _g(n, "arguments", []))
        return callee + opt + "(" + args + ")", _P_CALL

    def _arg(self, a):
        if _t(a) == "SpreadElement":
            return "..." + self.expr(_g(a, "argument"), _P_ASSIGN)
        return self.expr(a, _P_ASSIGN)

    def _e_NewExpression(self, n):
        cnode = _g(n, "callee")
        callee = self.expr(cnode, _P_CALL)
        # `new` binds looser than a call, so a call anywhere in the callee's
        # member chain (`new a.b()()` -> `new (a.b())()`) has to be wrapped
        # or it gets read as the argument list of the `new`.
        walk = cnode
        while _t(walk) == "MemberExpression":
            walk = _g(walk, "object")
        if _t(walk) == "CallExpression":
            callee = "(" + callee + ")"
        args = ("," + self.sp).join(self._arg(a) for a in _g(n, "arguments", []))
        return "new " + callee + "(" + args + ")", _P_CALL

    def _e_MemberExpression(self, n):
        onode = _g(n, "object")
        obj = self.expr(onode, _P_CALL)
        # `255.toString()` is a syntax error -- `255.` reads as a float and
        # then `toString` is "an identifier after a number". A numeric
        # literal that a `.` member follows needs parens (or a space, but
        # parens are unambiguous).
        if (_t(onode) == "Literal" and isinstance(_g(onode, "value"), (int, float))
                and not _g(onode, "regex") and not _g(n, "computed")
                and not any(c in obj for c in ".eExXoObBn")):
            obj = "(" + obj + ")"
        opt = _g(n, "optional")
        if _g(n, "computed"):
            return obj + ("?." if opt else "") + "[" + self.expr(_g(n, "property")) + "]", _P_CALL
        prop = _g(n, "property")
        pname = ("#" + _g(prop, "name")) if _t(prop) == "PrivateIdentifier" else _g(prop, "name")
        return obj + ("?." if opt else ".") + pname, _P_CALL

    def _e_ChainExpression(self, n):
        return self.expr(_g(n, "expression"), _P_CALL), _P_CALL

    def _e_ImportExpression(self, n):
        return "import(" + self.expr(_g(n, "source"), _P_ASSIGN) + ")", _P_CALL

    def _e_YieldExpression(self, n):
        star = "*" if _g(n, "delegate") else ""
        arg = _g(n, "argument")
        return "yield" + star + ((" " + self.expr(arg, _P_ASSIGN)) if arg is not None else ""), _P_ASSIGN

    def _e_AwaitExpression(self, n):
        return "await " + self.expr(_g(n, "argument"), _P_UNARY), _P_UNARY

    def _e_SpreadElement(self, n):
        return "..." + self.expr(_g(n, "argument"), _P_ASSIGN), _P_ASSIGN

    # -- patterns (destructuring / params) --------------------------
    def pattern(self, node):
        ty = _t(node)
        if ty in ("Identifier", "MemberExpression"):
            return self.expr(node)
        if ty == "AssignmentPattern":
            return self.pattern(_g(node, "left")) + self.sp + "=" + self.sp + self.expr(_g(node, "right"), _P_ASSIGN)
        if ty == "RestElement":
            return "..." + self.pattern(_g(node, "argument"))
        if ty == "ArrayPattern":
            els = _g(node, "elements", [])
            parts = [("" if e is None else self.pattern(e)) for e in els]
            return "[" + ("," + self.sp).join(parts) + "]"
        if ty == "ObjectPattern":
            props = _g(node, "properties", [])
            return "{" + self.sp + ("," + self.sp).join(self._pat_prop(p) for p in props) + self.sp + "}"
        return self.expr(node)

    def _pat_prop(self, p):
        if _t(p) == "RestElement":
            return "..." + self.pattern(_g(p, "argument"))
        key = self._key(p)
        val = _g(p, "value")
        if _g(p, "shorthand"):
            if _t(val) == "AssignmentPattern":
                return self.pattern(val)
            return key
        return key + ":" + self.sp + self.pattern(val)


def generate(node, *, minify=False, indent="  ", quote='"', semicolons=True):
    """Render an ESTree ``node`` (a ``Node`` tree or ``.to_dict()`` dict) to
    JavaScript source. ``minify=True`` strips all optional whitespace."""
    return _Gen(minify=minify, indent=indent, quote=quote, semi=semicolons).gen(node)


def minify(src_or_path, *, ecma_version=2022):
    """Read JavaScript (a source string, or a path to a ``.js`` file) and
    return it with all optional whitespace and comments removed."""
    import os

    from .parser import Parser

    text = src_or_path
    if isinstance(src_or_path, str) and "\n" not in src_or_path and len(src_or_path) < 4096 and os.path.isfile(src_or_path):
        with open(src_or_path, encoding="utf-8") as fh:
            text = fh.read()
    tree = Parser({"ecmaVersion": ecma_version, "locations": True,
                   "allowReturnOutsideFunction": True,
                   "allowAwaitOutsideFunction": True}, text).parse()
    return generate(tree, minify=True)

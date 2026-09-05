"""Python ``ast`` -> ESTree.

The front end of a small Python -> JavaScript transpiler: walk a CPython AST
and emit the ESTree dicts ``domonic_libs.acorn.generate`` turns into source.
A practical subset -- functions, classes, control flow, comprehensions,
f-strings, the common builtins -- with a JS runtime shim (``runtime.js``)
carrying the Python semantics JS doesn't share (truthiness of containers,
``range``, ``len``, negative indexing, ``in``, ``//`` ...).
"""

from __future__ import annotations

import ast

__all__ = ["translate", "PyJSError"]

_JS_RESERVED = {
    "arguments", "await", "break", "case", "catch", "class", "const", "continue",
    "debugger", "default", "delete", "do", "else", "enum", "eval", "export",
    "extends", "false", "finally", "for", "function", "if", "implements", "import",
    "in", "instanceof", "interface", "let", "new", "null", "package", "private",
    "protected", "public", "return", "static", "super", "switch", "this", "throw",
    "true", "typeof", "var", "void", "while", "with", "yield",
}

# the two stdlib modules that map onto JS built-ins (`Math`) + `__py` helpers
_STDLIB = {"math", "random"}

# builtins that map straight onto a `__py.<name>` runtime helper
_RT_BUILTINS = {
    "print", "range", "len", "str", "repr", "list", "tuple", "enumerate", "zip",
    "sorted", "sum", "min", "max", "abs", "round", "int", "float", "isinstance",
    "bool",
}
# builtins that map to a plain JS expression
_SIMPLE_BUILTINS = {
    "bool": ("__py", "bool"),
}
# builtin names that also work in value position (`map(str, xs)`, `key=len`) ->
# the `__py` attribute that implements them
_VALUE_BUILTINS = {
    n: n for n in (
        "len", "str", "repr", "list", "tuple", "dict", "set", "enumerate",
        "zip", "sorted", "sum", "min", "max", "abs", "round", "int", "float",
        "bool", "print", "range", "chr", "ord", "hex", "oct", "bin", "divmod",
        "reversed", "isinstance",
    )
}


class PyJSError(Exception):
    """A Python construct the transpiler doesn't (yet) support."""


def _id(name):
    if name in _JS_RESERVED:
        name = name + "$"
    return {"type": "Identifier", "name": name}


def _lit(value):
    if value is None:
        return {"type": "Literal", "value": None}
    if isinstance(value, bool):
        return {"type": "Literal", "value": value}
    if isinstance(value, (int, float)):
        return {"type": "Literal", "value": value}
    if isinstance(value, str):
        return {"type": "Literal", "value": value}
    if isinstance(value, bytes):
        return {"type": "Literal", "value": value.decode("latin-1")}
    raise PyJSError(f"unsupported constant {value!r}")


def _member(obj, prop, computed=False):
    return {"type": "MemberExpression", "object": obj,
            "property": prop if computed else _id(prop),
            "computed": computed, "optional": False}


def _call(callee, args):
    return {"type": "CallExpression", "callee": callee, "arguments": args, "optional": False}


def _rt(name, args):
    return _call(_member(_id("__py"), name), args)


def _expr_stmt(e):
    return {"type": "ExpressionStatement", "expression": e}


_BINOP = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%",
    ast.Pow: "**", ast.LShift: "<<", ast.RShift: ">>", ast.BitOr: "|",
    ast.BitXor: "^", ast.BitAnd: "&",
}
_CMP = {
    ast.Eq: "===", ast.NotEq: "!==", ast.Lt: "<", ast.LtE: "<=",
    ast.Gt: ">", ast.GtE: ">=", ast.Is: "===", ast.IsNot: "!==",
}
# comparisons that route through a `__py` helper for Python semantics
# (element-wise on lists/tuples/dicts, floored-sign-free ordering)
_CMP_RT = {
    ast.Eq: "eq", ast.NotEq: "ne", ast.Lt: "lt", ast.LtE: "le",
    ast.Gt: "gt", ast.GtE: "ge",
}
_BOOL_NODES = (ast.Compare, ast.BoolOp, ast.UnaryOp)


class _Tx:
    def __init__(self):
        self._class_stack = []
        self._scopes = [set()]   # names declared with `let` in each active scope
        self._pymods = {}        # `import math as m`  ->  {"m": "math"}
        self._pyfrom = {}        # `from math import pi`  ->  {"pi": ("math", "pi")}

    def _declared(self, name):
        return any(name in s for s in self._scopes)

    def _declare(self, name):
        self._scopes[-1].add(name)

    # -- module --------------------------------------------------------
    def module(self, tree):
        body = []
        for stmt in tree.body:
            out = self.stmt(stmt)
            body.extend(out if isinstance(out, list) else [out])
        return {"type": "Program", "sourceType": "module",
                "body": [b for b in body if b is not None]}

    # -- statements --------------------------------------------------
    def stmt(self, node):
        m = getattr(self, "_s_" + type(node).__name__, None)
        if m is None:
            raise PyJSError(f"unsupported statement: {type(node).__name__}")
        return m(node)

    def _block(self, stmts):
        out = []
        for s in stmts:
            r = self.stmt(s)
            out.extend(r if isinstance(r, list) else [r])
        return {"type": "BlockStatement", "body": [b for b in out if b is not None]}

    def _loop_body(self, stmts):
        # a JS `let` inside a loop body is block-scoped -- give the body its own
        # scope frame so a name first assigned here re-declares (not bare-assigns
        # against a now-out-of-scope `let`) when a *sibling* loop reuses it.
        self._scopes.append(set())
        try:
            return self._block(stmts)
        finally:
            self._scopes.pop()

    def _s_Pass(self, n):
        return {"type": "EmptyStatement"}

    def _s_Expr(self, n):
        # a bare string literal (docstring) -> drop it
        if isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            return None
        return _expr_stmt(self.expr(n.value))

    def _s_Import(self, n):
        for a in n.names:
            if a.name in _STDLIB:
                self._pymods[a.asname or a.name] = a.name
            else:
                raise PyJSError(
                    f"`import {a.name}` is not supported -- only `math` and `random` "
                    "map to JS; transpile a single self-contained module otherwise")
        return None

    def _s_ImportFrom(self, n):
        if n.level == 0 and n.module in _STDLIB:
            for a in n.names:
                self._pyfrom[a.asname or a.name] = (n.module, a.name)
            return None
        raise PyJSError("`import` is not supported -- transpile a single self-contained module")

    # -- `math` / `random`  ->  `Math` + `__py` -------------------------
    _MATH_CONST = {"pi": "PI", "e": "E", "inf": "Infinity", "nan": "NaN"}
    _MATH_FUNCS = {"sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
                   "sinh", "cosh", "tanh", "exp", "log2", "log10", "pow", "floor",
                   "ceil", "hypot", "sign", "trunc", "cbrt", "round", "abs",
                   "min", "max"}

    def _stdlib_member(self, mod, attr):
        if mod == "math":
            if attr == "tau":
                return {"type": "BinaryExpression", "operator": "*",
                        "left": _lit(2), "right": _member(_id("Math"), "PI")}
            if attr in self._MATH_CONST:
                return _member(_id("Math"), self._MATH_CONST[attr])
            if attr in self._MATH_FUNCS or attr == "log":
                return _member(_id("Math"), attr)
            raise PyJSError(f"`math.{attr}` has no JS equivalent")
        if mod == "random" and attr == "random":
            return _member(_id("Math"), "random")
        raise PyJSError(f"`random.{attr}` must be called, not referenced")

    def _stdlib_call(self, mod, fn, args):
        ja = [self.expr(a) for a in args]
        if mod == "math":
            if fn == "log" and len(ja) == 2:   # math.log(x, base)
                lg = lambda x: _call(_member(_id("Math"), "log"), [x])
                return {"type": "BinaryExpression", "operator": "/",
                        "left": lg(ja[0]), "right": lg(ja[1])}
            return _call(self._stdlib_member("math", fn), ja)
        # random.*
        if fn == "random":
            return _call(_member(_id("Math"), "random"), [])
        if fn in ("randint", "uniform", "choice", "randrange", "shuffle"):
            return _rt(fn, ja)
        if fn == "seed":
            return _id("undefined")
        raise PyJSError(f"`random.{fn}` is not supported")

    def _as_stdlib(self, node):
        """`node` -> a translated stdlib reference, or None if it isn't one."""
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id in self._pymods:
            return self._stdlib_member(self._pymods[node.value.id], node.attr)
        if isinstance(node, ast.Name) and node.id in self._pyfrom:
            return self._stdlib_member(*self._pyfrom[node.id])
        return None

    def _s_Assign(self, n):
        value = self.expr(n.value)
        stmts = []
        for i, target in enumerate(n.targets):
            v = value if i == 0 else self._target_ref(n.targets[0])
            stmts.append(self._assign_to(target, v, declare=(i == 0)))
        return [s for group in stmts for s in (group if isinstance(group, list) else [group])]

    def _target_ref(self, target):
        if isinstance(target, ast.Name):
            return _id(target.id)
        return self.expr(target)

    def _assign_to(self, target, value, *, declare, op=None):
        if isinstance(target, ast.Name):
            if op:
                return _expr_stmt({"type": "AssignmentExpression", "operator": op,
                                   "left": _id(target.id), "right": value})
            if declare and not self._declared(target.id):
                self._declare(target.id)
                return {"type": "VariableDeclaration", "kind": "let",
                        "declarations": [{"type": "VariableDeclarator",
                                          "id": _id(target.id), "init": value}]}
            return _expr_stmt({"type": "AssignmentExpression", "operator": "=",
                               "left": _id(target.id), "right": value})
        if isinstance(target, ast.Attribute):
            return _expr_stmt({"type": "AssignmentExpression", "operator": op or "=",
                               "left": _member(self.expr(target.value), target.attr),
                               "right": value})
        if isinstance(target, ast.Subscript):
            key = self._subscript_key(target.slice)
            return _expr_stmt(_rt("setitem", [self.expr(target.value), key, value]))
        if isinstance(target, (ast.Tuple, ast.List)):
            # a, b = ...  ->  [a, b] = __py.list(value)
            # self.x, obj[k] = ...  ->  a temp + sequential assigns
            if any(not isinstance(e, (ast.Name, ast.Starred)) for e in target.elts):
                tmp = _id("__t")
                out = [{"type": "VariableDeclaration", "kind": "const",
                        "declarations": [{"type": "VariableDeclarator", "id": tmp,
                                          "init": _rt("list", [value])}]}]
                for i, el in enumerate(target.elts):
                    out.append(self._assign_to(el, _rt("getitem", [tmp, _lit(i)]), declare=declare))
                return out
            elts = []
            for el in target.elts:
                if isinstance(el, ast.Starred):
                    elts.append({"type": "RestElement", "argument": _id(el.value.id)})
                else:
                    elts.append(_id(el.id))
            names = [el.value.id if isinstance(el, ast.Starred) else el.id for el in target.elts]
            fresh = declare and not any(self._declared(nm) for nm in names)
            if fresh:
                for nm in names:
                    self._declare(nm)
                return {"type": "VariableDeclaration", "kind": "let",
                        "declarations": [{"type": "VariableDeclarator",
                                          "id": {"type": "ArrayPattern", "elements": elts},
                                          "init": _rt("list", [value])}]}
            return _expr_stmt({"type": "AssignmentExpression", "operator": "=",
                               "left": {"type": "ArrayPattern", "elements": elts},
                               "right": _rt("list", [value])})
        raise PyJSError(f"unsupported assignment target: {type(target).__name__}")

    def _s_AugAssign(self, n):
        # `x <op>= v` where `x` is a subscript has to expand -- `__py.setitem`
        # takes the whole new value, there's no `+=` form of it. Names and
        # attributes keep the compact `x += v`.
        cur = ast.Subscript(value=n.target.value, slice=n.target.slice, ctx=ast.Load()) \
            if isinstance(n.target, ast.Subscript) else None
        # `//` and `%` need a helper, so there's no compound-assign form -- and
        # a subscript target has to expand anyway (`__py.setitem` wants the
        # whole new value). Everything else keeps the compact `x += v`.
        if isinstance(n.op, (ast.FloorDiv, ast.Mod)) or cur is not None:
            rhs = self._binop(n.op, self._aug_cur(n.target, cur), self.expr(n.value))
            return self._assign_to(n.target, rhs, declare=False)
        return self._assign_to(n.target, self.expr(n.value), declare=False,
                               op=_BINOP[type(n.op)] + "=")

    def _aug_cur(self, target, cur):
        return self.expr(cur) if cur is not None else self._target_ref(target)

    def _s_AnnAssign(self, n):
        if n.value is None:
            return None
        return self._assign_to(n.target, self.expr(n.value), declare=True)

    def _s_Return(self, n):
        return {"type": "ReturnStatement",
                "argument": self.expr(n.value) if n.value is not None else None}

    def _s_If(self, n):
        node = {"type": "IfStatement", "test": self._as_bool(n.test),
                "consequent": self._block(n.body), "alternate": None}
        if n.orelse:
            if len(n.orelse) == 1 and isinstance(n.orelse[0], ast.If):
                node["alternate"] = self.stmt(n.orelse[0])
            else:
                node["alternate"] = self._block(n.orelse)
        return node

    def _s_While(self, n):
        if n.orelse:
            raise PyJSError("`while ... else` is not supported")
        return {"type": "WhileStatement", "test": self._as_bool(n.test),
                "body": self._loop_body(n.body)}

    def _s_For(self, n):
        if n.orelse:
            raise PyJSError("`for ... else` is not supported")
        # for target in iter:  ->  for (const <target> of __py.iter(<iter>))
        target = self._for_target(n.target)
        return {"type": "ForOfStatement", "await": False,
                "left": {"type": "VariableDeclaration", "kind": "const",
                         "declarations": [{"type": "VariableDeclarator", "id": target, "init": None}]},
                "right": _rt("iter", [self.expr(n.iter)]),
                "body": self._loop_body(n.body)}

    def _for_target(self, t):
        if isinstance(t, ast.Name):
            return _id(t.id)
        if isinstance(t, (ast.Tuple, ast.List)):
            return {"type": "ArrayPattern", "elements": [self._for_target(e) for e in t.elts]}
        raise PyJSError("unsupported for-loop target")

    def _s_Break(self, n):
        return {"type": "BreakStatement", "label": None}

    def _s_Continue(self, n):
        return {"type": "ContinueStatement", "label": None}

    def _s_FunctionDef(self, n):
        self._declare(n.name)   # so a Capitalized helper (`IX`, `RGB`) isn't read as `new IX()`
        fn = self._function(n)
        fn["type"] = "FunctionDeclaration"
        return fn

    def _s_AsyncFunctionDef(self, n):
        self._declare(n.name)
        fn = self._function(n)
        fn["type"] = "FunctionDeclaration"
        fn["async"] = True
        return fn

    def _function(self, n, *, is_method=False):
        args = n.args
        params = []
        pos = list(args.args)
        if is_method and pos and pos[0].arg in ("self", "cls"):
            pos = pos[1:]
        defaults = list(args.defaults)
        ndef = len(defaults)
        for i, a in enumerate(pos):
            if i >= len(pos) - ndef:
                d = defaults[i - (len(pos) - ndef)]
                params.append({"type": "AssignmentPattern", "left": _id(a.arg),
                               "right": self.expr(d)})
            else:
                params.append(_id(a.arg))
        if args.vararg:
            params.append({"type": "RestElement", "argument": _id(args.vararg.arg)})
        if args.kwonlyargs or args.kwarg:
            raise PyJSError("keyword-only args / **kwargs are not supported yet")
        self._scopes.append({a.arg for a in pos}
                            | ({args.vararg.arg} if args.vararg else set()))
        try:
            body = self._block(n.body)
        finally:
            self._scopes.pop()
        # a Python function with no explicit return still returns None
        return {"type": "FunctionDeclaration", "id": _id(n.name), "params": params,
                "body": body, "generator": _has_yield(n), "async": False, "expression": False}

    def _s_ClassDef(self, n):
        if len(n.bases) > 1:
            raise PyJSError("multiple inheritance is not supported")
        superclass = self.expr(n.bases[0]) if n.bases and not _is_object_base(n.bases[0]) else None
        self._class_stack.append(n.name)
        members = []
        for item in n.body:
            if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant):
                continue  # docstring
            if isinstance(item, ast.FunctionDef):
                members.append(self._method(item))
            elif isinstance(item, ast.Assign):
                for t in item.targets:
                    if isinstance(t, ast.Name):
                        members.append({"type": "PropertyDefinition", "static": True,
                                        "computed": False, "key": _id(t.id),
                                        "value": self.expr(item.value)})
            elif isinstance(item, ast.Pass):
                pass
            else:
                raise PyJSError(f"unsupported class body item: {type(item).__name__}")
        self._class_stack.pop()
        return {"type": "ClassDeclaration", "id": _id(n.name), "superClass": superclass,
                "body": {"type": "ClassBody", "body": members}}

    def _method(self, n):
        fn = self._function(n, is_method=True)
        fn = {"type": "FunctionExpression", "id": None, "params": fn["params"],
              "body": fn["body"], "generator": fn["generator"], "async": False,
              "expression": False}
        name = n.name
        if name == "__init__":
            return {"type": "MethodDefinition", "static": False, "computed": False,
                    "kind": "constructor", "key": _id("constructor"), "value": fn}
        kind = "method"
        decos = {d.id for d in n.decorator_list if isinstance(d, ast.Name)}
        if "property" in decos:
            kind = "get"
        elif "staticmethod" in decos or "classmethod" in decos:
            return {"type": "MethodDefinition", "static": True, "computed": False,
                    "kind": "method", "key": _id(name), "value": fn}
        return {"type": "MethodDefinition", "static": False, "computed": False,
                "kind": kind, "key": _id(name), "value": fn}

    def _s_Raise(self, n):
        if n.exc is None:
            raise PyJSError("bare `raise` is not supported")
        arg = self.expr(n.exc)
        if isinstance(n.exc, ast.Call):
            # ValueError("msg") -> new Error("msg")
            msg = self.expr(n.exc.args[0]) if n.exc.args else _lit("")
            name = n.exc.func.id if isinstance(n.exc.func, ast.Name) else "Error"
            arg = {"type": "NewExpression", "callee": _id(_JS_ERR.get(name, "Error")),
                   "arguments": [msg]}
        return {"type": "ThrowStatement", "argument": arg}

    def _s_Try(self, n):
        if n.orelse:
            raise PyJSError("`try ... else` is not supported")
        block = self._block(n.body)
        handler = None
        if n.handlers:
            h = n.handlers[0]
            hbody = h.body
            param = _id(h.name) if h.name else _id("__err")
            handler = {"type": "CatchClause", "param": param, "body": self._block(hbody)}
        finalizer = self._block(n.finalbody) if n.finalbody else None
        return {"type": "TryStatement", "block": block, "handler": handler,
                "finalizer": finalizer}

    def _s_With(self, n):
        raise PyJSError("`with` is not supported")

    def _s_Global(self, n):
        return None

    _s_Nonlocal = _s_Global

    def _s_Delete(self, n):
        stmts = []
        for t in n.targets:
            if isinstance(t, ast.Subscript):
                stmts.append(_expr_stmt({"type": "UnaryExpression", "operator": "delete",
                                         "prefix": True,
                                         "argument": _member(self.expr(t.value),
                                                             self._subscript_key(t.slice), computed=True)}))
            elif isinstance(t, ast.Attribute):
                stmts.append(_expr_stmt({"type": "UnaryExpression", "operator": "delete",
                                         "prefix": True,
                                         "argument": _member(self.expr(t.value), t.attr)}))
            else:
                raise PyJSError("can only `del` a subscript or attribute")
        return stmts

    def _s_Assert(self, n):
        test = self._as_bool(n.test)
        msg = self.expr(n.msg) if n.msg else _lit("AssertionError")
        return {"type": "IfStatement",
                "test": {"type": "UnaryExpression", "operator": "!", "prefix": True, "argument": test},
                "consequent": {"type": "BlockStatement", "body": [
                    {"type": "ThrowStatement", "argument": {"type": "NewExpression",
                     "callee": _id("Error"), "arguments": [msg]}}]},
                "alternate": None}

    # -- expressions ----------------------------------------------
    def expr(self, node):
        m = getattr(self, "_e_" + type(node).__name__, None)
        if m is None:
            raise PyJSError(f"unsupported expression: {type(node).__name__}")
        return m(node)

    def _e_Constant(self, n):
        return _lit(n.value)

    def _e_Name(self, n):
        if n.id == "None":
            return _lit(None)
        if n.id == "True":
            return _lit(True)
        if n.id == "False":
            return _lit(False)
        if n.id == "self":
            return {"type": "ThisExpression"}
        std = self._as_stdlib(n)
        if std is not None:
            return std
        if n.id in _VALUE_BUILTINS and not self._declared(n.id):
            # a builtin used as a value -- `map(str, xs)`, `sort(key=len)`,
            # `isinstance(x, dict)` -- resolve to its `__py` implementation
            return _member(_id("__py"), _VALUE_BUILTINS[n.id])
        return _id(n.id)

    def _e_JoinedStr(self, n):
        quasis, exprs = [], []
        buf = ""
        for part in n.values:
            if isinstance(part, ast.Constant):
                buf += str(part.value)
            else:  # FormattedValue
                quasis.append({"type": "TemplateElement", "tail": False,
                               "value": {"raw": _tpl_escape(buf), "cooked": buf}})
                buf = ""
                exprs.append(self._formatted_value(part))
        quasis.append({"type": "TemplateElement", "tail": True,
                       "value": {"raw": _tpl_escape(buf), "cooked": buf}})
        return {"type": "TemplateLiteral", "quasis": quasis, "expressions": exprs}

    def _formatted_value(self, part):
        """One `{...}` slot of an f-string: value, then `!r`/`!s`/`!a`
        conversion, then a `:spec` handed to `__py.format`."""
        val = self.expr(part.value)
        conv = part.conversion
        if conv == 114:      # !r
            val = _rt("repr", [val])
        elif conv == 115:    # !s
            val = _rt("str", [val])
        elif conv == 97:     # !a  (no ascii() in JS -- repr is the closest)
            val = _rt("repr", [val])
        if part.format_spec is not None:
            spec = part.format_spec
            if (len(spec.values) == 1 and isinstance(spec.values[0], ast.Constant)):
                spec_node = _lit(str(spec.values[0].value))
            else:
                spec_node = self._e_JoinedStr(spec)
            return _rt("format", [val, spec_node])
        return val if conv in (114, 115, 97) else _rt("str", [val])

    def _e_FormattedValue(self, n):
        return self._e_JoinedStr(ast.JoinedStr(values=[n]))

    def _e_List(self, n):
        return {"type": "ArrayExpression",
                "elements": [self._maybe_spread(e) for e in n.elts]}

    _e_Tuple = _e_List

    def _maybe_spread(self, e):
        if isinstance(e, ast.Starred):
            return {"type": "SpreadElement", "argument": self.expr(e.value)}
        return self.expr(e)

    def _e_Set(self, n):
        return {"type": "NewExpression", "callee": _id("Set"),
                "arguments": [{"type": "ArrayExpression", "elements": [self.expr(e) for e in n.elts]}]}

    def _e_Dict(self, n):
        # A plain object only models string-keyed dicts faithfully: JS coerces
        # every key to a string and reorders integer-like keys. When any key
        # isn't a string literal, emit a real `Map` (the runtime helpers --
        # getitem / setitem / len / iter / items / str -- are all Map-aware).
        non_str = [k for k in n.keys
                   if k is not None and not (isinstance(k, ast.Constant)
                                             and isinstance(k.value, str))]
        if non_str:
            if any(k is None for k in n.keys):
                raise PyJSError("`{**d}` merged with a non-string key isn't "
                                "supported -- build it with `dict(...)` / update")
            entries = [{"type": "ArrayExpression",
                        "elements": [self.expr(k), self.expr(v)]}
                       for k, v in zip(n.keys, n.values)]
            return {"type": "NewExpression", "callee": _id("Map"),
                    "arguments": [{"type": "ArrayExpression", "elements": entries}]}
        props = []
        for k, v in zip(n.keys, n.values):
            if k is None:  # {**other}
                props.append({"type": "SpreadElement", "argument": self.expr(v)})
                continue
            props.append({"type": "Property", "kind": "init", "method": False,
                          "shorthand": False, "computed": False,
                          "key": self.expr(k), "value": self.expr(v)})
        return {"type": "ObjectExpression", "properties": props}

    # operators that mean something different on a `set` than on an `int`
    _SET_OP = {ast.BitAnd: "intersection", ast.BitOr: "union",
               ast.Sub: "difference", ast.BitXor: "symmetric_difference"}

    def _e_BinOp(self, n):
        if isinstance(n.op, ast.Mod) and _looks_stringy(n.left):
            raise PyJSError("`%`-string formatting is not supported -- use an f-string")
        if isinstance(n.op, ast.Mult) and (_is_seqish(n.left) or _is_seqish(n.right)):
            # Python sequence repetition: `[0.0] * n`, `"-" * 8`
            return _rt("mul", [self.expr(n.left), self.expr(n.right)])
        set_op = type(n.op) in self._SET_OP and (_is_settish(n.left) or _is_settish(n.right))
        return self._binop(n.op, self.expr(n.left), self.expr(n.right), set_op)

    def _binop(self, op, left, right, set_op=False):
        """One place that knows which Python operators need a `__py` helper to
        keep Python semantics: `//` floors, `%` is a floored modulo (JS `%`
        follows the sign of the dividend, Python the divisor). `& | ^ -` do set
        algebra only when an operand is syntactically a set -- for two plain
        variables, use `s.intersection(t)` / `.union` / `.difference`."""
        if isinstance(op, ast.FloorDiv):
            return _rt("floordiv", [left, right])
        if isinstance(op, ast.Mod):
            return _rt("mod", [left, right])
        if set_op:
            return _rt(self._SET_OP[type(op)], [left, right])
        return {"type": "BinaryExpression", "operator": _BINOP[type(op)],
                "left": left, "right": right}

    def _e_UnaryOp(self, n):
        if isinstance(n.op, ast.Not):
            return {"type": "UnaryExpression", "operator": "!", "prefix": True,
                    "argument": self._as_bool(n.operand)}
        op = {ast.UAdd: "+", ast.USub: "-", ast.Invert: "~"}[type(n.op)]
        return {"type": "UnaryExpression", "operator": op, "prefix": True,
                "argument": self.expr(n.operand)}

    def _e_BoolOp(self, n):
        op = "&&" if isinstance(n.op, ast.And) else "||"
        node = self.expr(n.values[0])
        for v in n.values[1:]:
            node = {"type": "LogicalExpression", "operator": op,
                    "left": node, "right": self.expr(v)}
        return node

    def _e_Compare(self, n):
        # chained: a < b < c  ->  a < b && b < c
        parts = []
        left_ast, prev = n.left, self.expr(n.left)
        for op, comp in zip(n.ops, n.comparators):
            r = self.expr(comp)
            if isinstance(op, ast.In):
                parts.append(_rt("contains", [prev, r]))
            elif isinstance(op, ast.NotIn):
                parts.append({"type": "UnaryExpression", "operator": "!", "prefix": True,
                              "argument": _rt("contains", [prev, r])})
            elif type(op) in _CMP_RT and not (_is_numish(left_ast) or _is_numish(comp)):
                # ==, !=, <, <=, >, >= compare containers element-wise in
                # Python; route through a helper unless one side is provably a
                # number (then the other must be too for valid Python, and the
                # bare JS operator is both faster and correct). `is` / `is not`
                # stay identity (=== / !==).
                parts.append(_rt(_CMP_RT[type(op)], [prev, r]))
            else:
                parts.append({"type": "BinaryExpression", "operator": _CMP[type(op)],
                              "left": prev, "right": r})
            left_ast, prev = comp, r
        node = parts[0]
        for p in parts[1:]:
            node = {"type": "LogicalExpression", "operator": "&&", "left": node, "right": p}
        return node

    def _e_IfExp(self, n):
        return {"type": "ConditionalExpression", "test": self._as_bool(n.test),
                "consequent": self.expr(n.body), "alternate": self.expr(n.orelse)}

    def _e_Lambda(self, n):
        fake = ast.FunctionDef(name="", args=n.args, body=[], decorator_list=[])
        f = self._function(fake)
        return {"type": "ArrowFunctionExpression", "id": None, "params": f["params"],
                "body": self.expr(n.body), "generator": False, "async": False,
                "expression": True}

    def _e_Call(self, n):
        # `Foo.new(...)` -- the cross-language "construct" idiom -> `new Foo(...)`
        if isinstance(n.func, ast.Attribute) and n.func.attr == "new":
            return {"type": "NewExpression", "callee": self.expr(n.func.value),
                    "arguments": [self._maybe_spread(a) for a in n.args]}
        # `math.*` / `random.*` (imported, or `from math import ...`)
        if isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                and n.func.value.id in self._pymods:
            return self._stdlib_call(self._pymods[n.func.value.id], n.func.attr, n.args)
        if isinstance(n.func, ast.Name) and n.func.id in self._pyfrom:
            return self._stdlib_call(*self._pyfrom[n.func.id], n.args)
        # builtins
        if isinstance(n.func, ast.Name):
            name = n.func.id
            if name in _RT_BUILTINS:
                jsargs = [self.expr(a) for a in n.args]
                if name == "sorted":
                    opts = self._kw_opts(n.keywords, {"key", "reverse"})
                    return _rt("sorted", [jsargs[0], opts])
                if name == "enumerate" and len(jsargs) == 1:
                    return _rt("enumerate", jsargs)
                if name in ("min", "max"):
                    kw = {k.arg: k.value for k in n.keywords}
                    if "key" in kw or "default" in kw:
                        seq = jsargs[0] if len(jsargs) == 1 else \
                            {"type": "ArrayExpression", "elements": jsargs}
                        by = [seq, self.expr(kw["key"]) if "key" in kw else _lit(None)]
                        if "default" in kw:
                            by.append(self.expr(kw["default"]))
                        return _rt(name + "by", by)
                return _rt(name, jsargs)
            if name in ("chr", "ord", "hex", "oct", "bin", "divmod", "reversed"):
                return _rt(name, [self.expr(a) for a in n.args])
            if name == "dict" and not n.args:
                return {"type": "ObjectExpression", "properties": []}
            if name in ("set", "frozenset"):
                return {"type": "NewExpression", "callee": _id("Set"),
                        "arguments": [self.expr(a) for a in n.args]}
            if name == "next":
                g = self.expr(n.args[0])
                return _member(_call(_member(g, "next"), []), "value")
            if name in ("map", "filter") and len(n.args) == 2:
                fn, it = self.expr(n.args[0]), _rt("list", [self.expr(n.args[1])])
                return _call(_member(it, name), [fn])
            if name == "any":
                return _call(_member(_rt("list", [self.expr(n.args[0])]), "some"), [_id("Boolean")])
            if name == "all":
                return _call(_member(_rt("list", [self.expr(n.args[0])]), "every"), [_id("Boolean")])
            if name == "type" and len(n.args) == 1:
                return _member(_member(self.expr(n.args[0]), "constructor"), "name")
        # method calls that need Python semantics
        if isinstance(n.func, ast.Attribute):
            translated = self._method_call(n.func, n.args, n.keywords)
            if translated is not None:
                return translated
        callee = self.expr(n.func)
        args = [self._maybe_spread(a) for a in n.args]
        if n.keywords:
            # f(x, k=v) -> f(x, {k: v})   (best effort)
            obj = {"type": "ObjectExpression", "properties": [
                {"type": "Property", "kind": "init", "method": False, "shorthand": False,
                 "computed": kw.arg is None, "key": _id(kw.arg) if kw.arg else self.expr(kw.value),
                 "value": self.expr(kw.value)} for kw in n.keywords if kw.arg]}
            args.append(obj)
        # a class instantiation: Foo(...) where Foo is Capitalized -> new Foo(...)
        # -- unless it's a plain function we've seen `def`d (a Capitalized helper)
        if (isinstance(n.func, ast.Name) and n.func.id[:1].isupper()
                and n.func.id not in _JS_ERR and not self._declared(n.func.id)):
            return {"type": "NewExpression", "callee": callee, "arguments": args}
        return _call(callee, args)

    def _kw_opts(self, keywords, allowed):
        props = []
        for kw in keywords:
            if kw.arg in allowed:
                props.append({"type": "Property", "kind": "init", "method": False,
                              "shorthand": False, "computed": False,
                              "key": _id(kw.arg), "value": self.expr(kw.value)})
        return {"type": "ObjectExpression", "properties": props}

    # dict/list/set/str methods whose Python semantics differ from any JS
    # method of the same name -> `__py.<name>(obj, ...args)` (polymorphic in
    # the runtime, since the receiver's type isn't known here)
    _RT_METHODS = {
        "items", "keys", "values", "get", "pop", "setdefault", "update",
        "copy", "clear", "popitem", "extend", "insert", "remove", "index",
        "count", "add", "discard", "union", "intersection", "difference",
        "symmetric_difference", "issubset", "issuperset",
        "title", "capitalize", "swapcase", "zfill", "center", "splitlines",
        "removeprefix", "removesuffix", "isdigit", "isalpha", "isalnum",
        "isspace", "isupper", "islower", "sort",
    }
    # str methods that map 1:1 onto a JS String method (same arg meaning)
    _STR_PASSTHROUGH = {
        "upper": "toUpperCase", "lower": "toLowerCase", "casefold": "toLowerCase",
        "find": "indexOf", "rfind": "lastIndexOf",
        "ljust": "padEnd", "rjust": "padStart",
        "startswith": "startsWith", "endswith": "endsWith",
    }

    def _method_call(self, attr, args, keywords):
        name = attr.attr
        obj = self.expr(attr.value)
        jsargs = [self.expr(a) for a in args]
        if name == "append":
            return _call(_member(obj, "push"), jsargs)
        if name == "format":
            return _rt("fmt", [obj] + jsargs)
        if name == "sort":
            return _rt("sort", [obj, self._kw_opts(keywords, {"key", "reverse"})])
        if name in ("strip", "lstrip", "rstrip"):
            if jsargs:   # `.strip(chars)` -- JS trim* take no argument
                side = {"strip": 0, "lstrip": -1, "rstrip": 1}[name]
                return _rt("strip", [obj, jsargs[0], _lit(side)])
            js = {"strip": "trim", "lstrip": "trimStart", "rstrip": "trimEnd"}[name]
            return _call(_member(obj, js), [])
        if name == "join":
            return _call(_member(_rt("list", jsargs), "join"), [obj])
        if name == "split":
            return _rt("split", [obj] + jsargs)   # runtime handles the no-arg whitespace case
        if name == "replace":
            return _rt("replace", [obj] + jsargs)
        if name in self._STR_PASSTHROUGH:
            return _call(_member(obj, self._STR_PASSTHROUGH[name]), jsargs)
        if name in self._RT_METHODS:
            return _rt(name, [obj] + jsargs)
        return None  # fall through to a plain method call

    def _e_Attribute(self, n):
        std = self._as_stdlib(n)
        if std is not None:
            return std
        return _member(self.expr(n.value), n.attr)

    def _e_Subscript(self, n):
        if isinstance(n.slice, ast.Slice):
            s = n.slice
            return _rt("slice", [self.expr(n.value),
                                 self.expr(s.lower) if s.lower else _lit(None),
                                 self.expr(s.upper) if s.upper else _lit(None),
                                 self.expr(s.step) if s.step else _lit(None)])
        return _rt("getitem", [self.expr(n.value), self._subscript_key(n.slice)])

    def _subscript_key(self, s):
        return self.expr(s)

    def _e_Starred(self, n):
        return {"type": "SpreadElement", "argument": self.expr(n.value)}

    def _e_ListComp(self, n):
        return self._comprehension(n, kind="list")

    def _e_GeneratorExp(self, n):
        return self._comprehension(n, kind="list")

    def _e_SetComp(self, n):
        return {"type": "NewExpression", "callee": _id("Set"),
                "arguments": [self._comprehension(n, kind="list")]}

    def _e_DictComp(self, n):
        pairs = self._comprehension(n, kind="dict")
        return _call(_member(_id("Object"), "fromEntries"), [pairs])

    def _comprehension(self, n, *, kind):
        if len(n.generators) != 1:
            raise PyJSError("only single-`for` comprehensions are supported")
        g = n.generators[0]
        src = _rt("list", [self.expr(g.iter)])
        param = self._for_target(g.target)
        for cond in g.ifs:
            src = _call(_member(src, "filter"), [self._arrow(param, self._as_bool(cond))])
        if kind == "dict":
            body = {"type": "ArrayExpression", "elements": [self.expr(n.key), self.expr(n.value)]}
        else:
            body = self.expr(n.elt)
        return _call(_member(src, "map"), [self._arrow(param, body)])

    def _arrow(self, param, body):
        return {"type": "ArrowFunctionExpression", "id": None,
                "params": [param], "body": body, "generator": False,
                "async": False, "expression": True}

    def _e_Await(self, n):
        return {"type": "AwaitExpression", "argument": self.expr(n.value)}

    def _e_Yield(self, n):
        return {"type": "YieldExpression", "delegate": False,
                "argument": self.expr(n.value) if n.value else None}

    def _e_YieldFrom(self, n):
        return {"type": "YieldExpression", "delegate": True, "argument": self.expr(n.value)}

    # -- helpers ----------------------------------------------------
    def _as_bool(self, node):
        """Wrap a test-position expression in `__py.bool()` unless it's
        already a boolean-producing node."""
        e = self.expr(node)
        if isinstance(node, _BOOL_NODES):
            return e
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return e
        return _rt("bool", [e])


_JS_ERR = {
    "Exception": "Error", "ValueError": "Error", "TypeError": "TypeError",
    "RuntimeError": "Error", "KeyError": "Error", "IndexError": "RangeError",
    "RangeError": "RangeError", "NotImplementedError": "Error",
    "AttributeError": "Error", "ZeroDivisionError": "Error", "StopIteration": "Error",
}


def _tpl_escape(s):
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def _is_object_base(node):
    return isinstance(node, ast.Name) and node.id == "object"


def _looks_stringy(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


_NUMISH_CALLS = {"len", "ord", "int", "abs", "round", "hash", "id"}


_SET_CALLS = {"set", "frozenset", "union", "intersection", "difference",
              "symmetric_difference", "copy"}


def _is_seqish(node):
    if isinstance(node, (ast.List, ast.Tuple, ast.ListComp, ast.JoinedStr)):
        return True
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _is_settish(node):
    if isinstance(node, (ast.Set, ast.SetComp)):
        return True
    if isinstance(node, ast.Call):
        f = node.func
        return (isinstance(f, ast.Name) and f.id in _SET_CALLS) or \
               (isinstance(f, ast.Attribute) and f.attr in _SET_CALLS)
    if isinstance(node, ast.BinOp):
        return _is_settish(node.left) or _is_settish(node.right)
    return False


def _is_numish(node):
    """True when `node` is provably a number -- so a comparison against it is
    a plain numeric one and needs no element-wise helper."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float)) and not isinstance(node.value, bool)
    if isinstance(node, ast.BinOp):
        return not isinstance(node.op, ast.Add)   # `+` might be list/str concat
    if isinstance(node, ast.UnaryOp):
        return isinstance(node.op, (ast.USub, ast.UAdd, ast.Invert))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in _NUMISH_CALLS
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr in ("count", "index", "find", "rfind")
    return False


def _has_yield(fn):
    for node in ast.walk(fn):
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not fn:
            return False
    return False


def translate(source):
    """Python source -> an ESTree ``Program`` dict. Raises :class:`PyJSError`
    for a construct outside the supported subset, and ``SyntaxError`` for
    invalid Python."""
    tree = ast.parse(source)
    return _Tx().module(tree)

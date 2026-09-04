"""Turn JSX source into domonic Python.

``jsx_to_python(src)`` returns a Python expression string that builds the same
tree with ``domonic.html`` factories (or, with ``mode="h"``, with the preact
port's ``h(...)`` hyperscript). JS expressions inside ``{ ... }`` and attribute
values are passed through verbatim from the source -- this transforms the markup
layer, not arbitrary JavaScript.
"""

from __future__ import annotations

import keyword
import re

from . import parse_jsx

# JSX attribute name -> domonic kwarg name (the rest get a leading underscore).
_ATTR_MAP = {
    "className": "_class",
    "class": "_class",
    "htmlFor": "_for",
    "for": "_for",
}

_HTML_TAGS = {
    "a", "abbr", "address", "area", "article", "aside", "audio", "b", "base", "bdi",
    "bdo", "blockquote", "body", "br", "button", "canvas", "caption", "cite", "code",
    "col", "colgroup", "data", "datalist", "dd", "del", "details", "dfn", "dialog",
    "div", "dl", "dt", "em", "embed", "fieldset", "figcaption", "figure", "footer",
    "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hr", "html", "i",
    "iframe", "img", "input", "ins", "kbd", "label", "legend", "li", "link", "main",
    "map", "mark", "menu", "meta", "meter", "nav", "noscript", "object", "ol",
    "optgroup", "option", "output", "p", "picture", "pre", "progress", "q", "rp",
    "rt", "ruby", "s", "samp", "script", "section", "select", "slot", "small",
    "source", "span", "strong", "style", "sub", "summary", "sup", "table", "tbody",
    "td", "template", "textarea", "tfoot", "th", "thead", "time", "title", "tr",
    "track", "u", "ul", "var", "video", "wbr",
}
_SVG_TAGS = {"svg", "path", "circle", "rect", "line", "polygon", "polyline",
             "ellipse", "g", "text", "tspan", "defs", "use", "symbol", "marker"}


def _attr_kw(name):
    if name in _ATTR_MAP:
        return _ATTR_MAP[name]
    if re.match(r"^on[A-Z]", name):
        return "_" + name.lower()
    kw = "_" + name.replace("-", "_")
    return kw


def _jsx_text(raw):
    """JSX whitespace: trim each line, drop blank lines, collapse newlines to one
    space; a chunk that is only whitespace-with-a-newline vanishes."""
    lines = raw.split("\n")
    if len(lines) == 1:
        return raw if raw.strip() or " " not in raw or "\t" not in raw else raw
    parts = [ln.strip() for ln in lines]
    parts = [p for p in parts if p]
    return " ".join(parts)


class _T:
    def __init__(self, src, mode):
        self.src = src
        self.mode = mode
        self.tags = set()  # lowercase factory names used (for the import line)
        self.svg = set()

    def slice(self, node):
        return self.src[node["start"]:node["end"]]

    def expr(self, node):
        """A JS expression as Python source. Object literals (``style={{...}}``)
        are converted to dict syntax; everything else is passed through."""
        if node["type"] == "ObjectExpression":
            return self._obj(node)
        return self.slice(node)

    _NON_PX = {"opacity", "zIndex", "fontWeight", "lineHeight", "flex", "flexGrow",
               "flexShrink", "order", "zoom", "gridRow", "gridColumn"}

    def _style(self, node):
        """``style={{...}}`` -> a CSS string when every value is a literal
        (React camelCase -> kebab-case, bare numbers get ``px``); otherwise the
        object stays a dict (domonic's ``_style`` does not yet accept one)."""
        parts = []
        for p in node["properties"]:
            if p["type"] != "Property" or p.get("computed") or p["key"]["type"] not in ("Identifier", "Literal"):
                return self._obj(node)
            v = p["value"]
            if v["type"] != "Literal":
                return self._obj(node)
            name = p["key"].get("name") or p["key"].get("value")
            prop = re.sub(r"([A-Z])", r"-\1", name).lower()
            val = v["value"]
            if isinstance(val, float) and val.is_integer():
                val = int(val)
            if isinstance(val, (int, float)) and not isinstance(val, bool) and name not in self._NON_PX:
                val = f"{val}px"
            parts.append(f"{prop}: {val}")
        return repr("; ".join(parts))

    def _obj(self, node):
        items = []
        for p in node["properties"]:
            if p["type"] == "SpreadElement":
                items.append("**" + self.expr(p["argument"]))
                continue
            k = p["key"]
            if p.get("computed"):
                key = "[" + self.slice(k) + "]"  # not valid dict syntax; flagged
            elif k["type"] == "Identifier":
                key = repr(k["name"])
            elif k["type"] == "Literal":
                key = repr(k["value"])
            else:
                key = self.slice(k)
            items.append(f"{key}: {self.expr(p['value'])}")
        return "{" + ", ".join(items) + "}"

    def name_of(self, node):
        t = node["type"]
        if t == "JSXIdentifier":
            return node["name"]
        if t == "JSXNamespacedName":
            return node["namespace"]["name"] + ":" + node["name"]["name"]
        if t == "JSXMemberExpression":
            return self.name_of(node["object"]) + "." + self.name_of(node["property"])
        return "?"

    def tag_token(self, node):
        """Return (code, is_host) for the element name."""
        name = self.name_of(node) if node else None
        if name is None:
            return None, False
        host = "." not in name and ":" not in name and name[:1].islower()
        if host:
            fac = name if not keyword.iskeyword(name) else name + "_"
            if name in _SVG_TAGS:
                self.svg.add(name)
            else:
                self.tags.add(name)
            return (f'"{name}"' if self.mode == "h" else fac), True
        return (f'"{name}"' if self.mode == "h" else name), False

    def attrs(self, attrs):
        pos, kw, spreads = [], [], []
        for a in attrs:
            if a["type"] == "JSXSpreadAttribute":
                spreads.append("**" + self.slice(a["argument"]))
                continue
            name = self.name_of(a["name"])
            key = _attr_kw(name)
            val = a["value"]
            if val is None:
                expr = '""'
            elif val["type"] == "Literal":
                expr = repr(val["value"])
            elif val["type"] == "JSXExpressionContainer":
                inner = val["expression"]
                if name == "style" and inner["type"] == "ObjectExpression":
                    expr = self._style(inner)
                else:
                    expr = self.jsx_expr(inner)
            elif val["type"] in ("JSXElement", "JSXFragment"):
                expr = self.element(val)
            else:
                expr = self.slice(val)
            kw.append(f"{key}={expr}")
        return pos, kw, spreads

    def children(self, kids):
        out = []
        for c in kids:
            t = c["type"]
            if t in ("JSXText", "Literal"):
                txt = _jsx_text(c.get("value") or c.get("raw") or "")
                if txt:
                    out.append(repr(txt))
            elif t == "JSXExpressionContainer":
                e = c["expression"]
                if e["type"] == "JSXEmptyExpression":
                    continue
                out.append(self.jsx_expr(e))
            elif t in ("JSXElement", "JSXFragment"):
                out.append(self.element(c))
        return out

    @staticmethod
    def _param_name(p):
        return p["name"] if p["type"] == "Identifier" else None

    def jsx_expr(self, node):
        """Render a JS expression that may embed JSX.

        Handles the three control-flow shapes React code uses to put markup in
        ``{ ... }``: ``cond && <X/>``, ``cond ? <A/> : <B/>`` and
        ``list.map(x => <li/>)``. Anything else is passed through verbatim.
        """
        t = node["type"]
        if t in ("JSXElement", "JSXFragment"):
            return self.element(node)
        if t == "ObjectExpression":
            return self._obj(node)
        if t == "LogicalExpression" and node["operator"] == "&&":
            return f"({self.jsx_expr(node['right'])} if ({self.slice(node['left'])}) else '')"
        if t == "LogicalExpression" and node["operator"] == "||":
            return f"(({self.slice(node['left'])}) or {self.jsx_expr(node['right'])})"
        if t == "ConditionalExpression":
            return (f"({self.jsx_expr(node['consequent'])} if ({self.slice(node['test'])}) "
                    f"else {self.jsx_expr(node['alternate'])})")
        if t == "CallExpression":
            callee = node["callee"]
            args = node["arguments"]
            if (callee["type"] == "MemberExpression" and not callee.get("computed")
                    and callee["property"].get("name") == "map" and args
                    and args[0]["type"] in ("ArrowFunctionExpression", "FunctionExpression")
                    and args[0]["body"]["type"] != "BlockStatement"):
                arrow = args[0]
                names = [self._param_name(p) for p in arrow["params"]]
                if all(names):
                    obj = self.slice(callee["object"])
                    rendered = self.jsx_expr(arrow["body"])
                    if len(names) >= 2:  # (item, index) => ...
                        return f"[{rendered} for {names[1]}, {names[0]} in enumerate({obj})]"
                    return f"[{rendered} for {names[0]} in {obj}]"
        return self.slice(node)

    def element(self, node):
        if node["type"] == "JSXFragment":
            kids = self.children(node["children"])
            if self.mode == "h":
                return "h(Fragment, None" + ("".join(", " + k for k in kids)) + ")"
            return "[" + ", ".join(kids) + "]"
        opening = node["openingElement"]
        code, _host = self.tag_token(opening.get("name"))
        _pos, kw, spreads = self.attrs(opening["attributes"])
        kids = self.children(node["children"])
        if self.mode == "h":
            props = "{" + ", ".join(f'"{k.split("=")[0]}": {k.split("=", 1)[1]}' for k in kw) + "}" if kw else "None"
            if spreads:
                props = "{" + ", ".join(
                    (f'"{k.split("=")[0]}": {k.split("=", 1)[1]}' for k in kw)
                ) + ("" if not kw else ", ") + ", ".join(s.replace("**", "**") for s in spreads) + "}"
            args = [code, props] + kids
            return "h(" + ", ".join(args) + ")"
        args = kids + kw + spreads
        return f"{code}(" + ", ".join(args) + ")"

    def import_line(self):
        lines = []
        if self.mode == "h":
            lines.append("from domonic_libs.preact import h")
        if self.tags:
            lines.append("from domonic.html import " + ", ".join(sorted(self.tags)))
        if self.svg:
            lines.append("from domonic.svg import " + ", ".join(sorted(self.svg)))
        return "\n".join(lines)


def jsx_to_python(src, mode="domonic", ecma_version=2022, with_imports=False):
    """Transform a JSX expression / statement string to domonic Python.

    ``mode="domonic"`` emits ``div(_class="x", "hi")``; ``mode="h"`` emits
    ``h("div", {...}, "hi")``. With ``with_imports=True`` the needed import
    lines are prepended.
    """
    tree = parse_jsx(src, {"ecmaVersion": ecma_version}).to_dict()
    t = _T(src, mode)

    def render_expr(node):
        return t.jsx_expr(node)

    body = tree["body"]
    out = []
    for stmt in body:
        if stmt["type"] == "ExpressionStatement":
            out.append(render_expr(stmt["expression"]))
        elif stmt["type"] == "VariableDeclaration":
            parts = []
            for d in stmt["declarations"]:
                init = d.get("init")
                rhs = render_expr(init) if init else "None"
                parts.append(f"{t.src[d['id']['start']:d['id']['end']]} = {rhs}")
            out.append("\n".join(parts))
        else:
            out.append(t.src[stmt["start"]:stmt["end"]])
    code = "\n".join(out)
    if with_imports:
        imp = t.import_line()
        return (imp + "\n\n" + code) if imp else code
    return code

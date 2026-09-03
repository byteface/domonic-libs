# Ported from preactjs/preact (MIT), tag 10.29.8. Preserve the upstream licence
# when redistributing. Mirrors src/constants.js.
"""Bit flags, namespace URIs and shared empty singletons used by the reconciler.

Python has no ``undefined``, so the port introduces an ``UNDEFINED`` sentinel
distinct from ``None`` (which stands in for JavaScript ``null``). A handful of
Preact code paths genuinely depend on the ``null`` vs ``undefined`` distinction
-- most visibly ``value``/``checked`` prop handling in ``diffElementNodes`` --
so the sentinel is not merely cosmetic.
"""

from __future__ import annotations

# Normal hydration that attaches to a DOM tree but does not diff it.
MODE_HYDRATE = 1 << 5
# Signifies this VNode suspended on the previous render.
MODE_SUSPENDED = 1 << 7
# Indicates that this node needs to be inserted while patching children.
INSERT_VNODE = 1 << 2
# Indicates a VNode has been matched with another VNode in the diff.
MATCHED = 1 << 1

# Reset all mode flags.
RESET_MODE = ~(MODE_HYDRATE | MODE_SUSPENDED)

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
MATH_NAMESPACE = "http://www.w3.org/1998/Math/MathML"

NULL = None


class _Undefined:
    """Singleton standing in for JavaScript ``undefined``."""

    __slots__ = ()
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):  # pragma: no cover - debugging aid
        return "UNDEFINED"

    def __bool__(self):
        return False


UNDEFINED = _Undefined()

EMPTY_OBJ = {}
EMPTY_ARR = []

# Matches CSS properties that take a raw number rather than a pixel length.
IS_NON_DIMENSIONAL = r"acit|ex(?:s|g|n|p|$)|rph|grid|ows|mnc|ntw|ine[ch]|zoo|^ord|itera"

# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/util.js.
"""Small helpers: ``assign``, ``isArray``, ``removeNode`` and ``some``.

``some`` reproduces ``Array.prototype.some`` -- iterate, and stop early as soon
as the callback returns a truthy value. Preact leans on that short-circuit in a
couple of places (``updateParentDomPointers``, ``markAsForce``); elsewhere
``.some`` is just a byte-saving ``forEach`` and a plain ``for`` loop does.
"""

from __future__ import annotations


def is_array(value):
    return isinstance(value, list)


def assign(obj, props):
    """``Object.assign`` for exactly two operands (copies own enumerable keys)."""
    for key in props:
        obj[key] = props[key]
    return obj


def remove_node(node):
    """Detach ``node`` from its parent if it is currently attached."""
    if node is not None and getattr(node, "parentNode", None) is not None:
        node.parentNode.removeChild(node)


def some(iterable, fn):
    """``Array.prototype.some`` -- returns ``True`` on the first truthy callback."""
    for item in list(iterable):
        if fn(item):
            return True
    return False

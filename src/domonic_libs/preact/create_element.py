# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/create-element.js.
"""``createElement`` / ``h``, ``createVNode``, ``Fragment``, ``createRef``.

There is no JSX in Python, so ``h(type, props, *children)`` is the authoring
API. Preact's vnodes are plain objects with a frozen ``constructor === undefined``
marker; the port uses a ``VNode`` class with ``__slots__`` instead and treats
``isinstance(x, VNode)`` as the equivalent identity check.
"""

from __future__ import annotations

from .constants import NULL, UNDEFINED
from .options import options

_vnode_id = 0


class VNode:
    """A virtual DOM node. Fields prefixed ``_`` are reconciler bookkeeping."""

    __slots__ = (
        "type",
        "props",
        "key",
        "ref",
        "_children",
        "_parent",
        "_depth",
        "_dom",
        "_component",
        "_original",
        "_index",
        "_flags",
        "_mask",
    )

    def __repr__(self):  # pragma: no cover - debugging aid
        t = self.type
        name = getattr(t, "__name__", t)
        return f"<VNode {name!r} key={self.key!r}>"


def create_element(type, props=None, *children):
    """``h(type, props, *children)`` -- normalise props, split out key/ref."""
    normalized_props = {}
    key = NULL
    ref = NULL
    if props:
        for name in props:
            if name == "key":
                key = props[name]
            elif name == "ref":
                ref = props[name]
            else:
                normalized_props[name] = props[name]

    if children:
        normalized_props["children"] = children[0] if len(children) == 1 else list(children)

    # If a component vnode, apply its defaultProps for any prop left unset.
    if callable(type) and getattr(type, "defaultProps", NULL) is not NULL:
        for name in type.defaultProps:
            if normalized_props.get(name, UNDEFINED) is UNDEFINED:
                normalized_props[name] = type.defaultProps[name]

    return create_vnode(type, normalized_props, key, ref, NULL)


def create_vnode(type, props, key, ref, original):
    """Low-level vnode allocation (used internally and by ``cloneElement``)."""
    global _vnode_id
    vnode = VNode()
    vnode.type = type
    vnode.props = props
    vnode.key = key
    vnode.ref = ref
    vnode._children = NULL
    vnode._parent = NULL
    vnode._depth = 0
    vnode._dom = NULL
    vnode._component = NULL
    vnode._index = -1
    vnode._flags = 0
    vnode._mask = NULL
    if original is NULL:
        _vnode_id += 1
        vnode._original = _vnode_id
    else:
        vnode._original = original

    # Only invoke the vnode hook if this was *not* a direct copy.
    if original is NULL and options.vnode is not NULL:
        options.vnode(vnode)

    return vnode


def clone_vnode(vnode):
    """``assign({}, vnode)`` -- a shallow copy that is *not* a fresh original."""
    copy = VNode()
    for name in VNode.__slots__:
        setattr(copy, name, getattr(vnode, name))
    return copy


def create_ref():
    return {"current": NULL}


def Fragment(props, *_context):
    # Called both as ``Fragment(props)`` and, via the PFC render shim, as
    # ``Fragment(props, context)``; the extra arg is ignored (JS parity).
    return props.get("children")


def is_valid_element(vnode):
    return isinstance(vnode, VNode)


# Sentinel used by the reconciler wherever Preact passes ``EMPTY_OBJ`` in an
# *old vnode* position. Python cannot read ``undefined`` off a bare ``{}``, so
# this is a real (frozen-ish) VNode whose ``_original`` can never match a live
# one. ``EMPTY_OBJ`` (a dict) is still used for the global-context position.
EMPTY_VNODE = create_vnode(NULL, NULL, NULL, NULL, object())


# Aliases matching Preact's public names.
createElement = create_element
h = create_element
createVNode = create_vnode
createRef = create_ref
isValidElement = is_valid_element

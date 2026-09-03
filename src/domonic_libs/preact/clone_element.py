# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/clone-element.js.
"""``clone_element`` -- copy a vnode, merging extra props and replacing children."""

from __future__ import annotations

from .constants import NULL, UNDEFINED
from .create_element import create_vnode
from .util import assign


def clone_element(vnode, props=None, *children):
    normalized_props = assign({}, dict(vnode.props))
    key = NULL
    ref = NULL

    default_props = None
    if vnode.type and getattr(vnode.type, "defaultProps", None):
        default_props = vnode.type.defaultProps

    if props:
        for name in props:
            if name == "key":
                key = props[name]
            elif name == "ref":
                ref = props[name]
            elif props[name] is UNDEFINED and default_props is not None:
                normalized_props[name] = default_props[name]
            else:
                normalized_props[name] = props[name]

    if children:
        normalized_props["children"] = (
            children[0] if len(children) == 1 else list(children)
        )

    return create_vnode(
        vnode.type,
        normalized_props,
        key or vnode.key,
        ref or vnode.ref,
        NULL,
    )


cloneElement = clone_element

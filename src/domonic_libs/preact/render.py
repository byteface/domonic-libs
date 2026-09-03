# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/render.js.
"""``render`` / ``hydrate`` -- mount or update a vnode tree into a DOM container.

The last-rendered tree is stashed on the container as ``container._children`` so
that a second ``render`` into the same node diffs rather than re-mounts.
"""

from __future__ import annotations

from domonic.dom import document

from .component import begin_batch, end_batch
from .constants import EMPTY_OBJ, NULL
from .create_element import EMPTY_VNODE, create_element, Fragment
from .diff.index import commit_root, diff
from .options import options


def render(vnode, parent_dom, replace_node=None):
    if parent_dom is document:
        parent_dom = document.documentElement

    if options._root:
        options._root(vnode, parent_dom)

    # hydrate() smuggles itself in through replace_node to flag hydration mode.
    is_hydrating = callable(replace_node)

    old_vnode = (
        NULL
        if is_hydrating
        else (
            (replace_node._children if replace_node is not None else None)
            or getattr(parent_dom, "_children", None)
        )
    )

    wrapper = create_element(Fragment, NULL, vnode)
    if not is_hydrating and replace_node is not None:
        replace_node._children = wrapper
    else:
        parent_dom._children = wrapper
    vnode = wrapper

    commit_queue = []
    ref_queue = []

    first_child = getattr(parent_dom, "firstChild", None)
    if not is_hydrating and replace_node is not None and not callable(replace_node):
        excess = [replace_node]
    elif old_vnode:
        excess = NULL
    elif first_child:
        excess = list(parent_dom.childNodes)
    else:
        excess = NULL

    if not is_hydrating and replace_node is not None and not callable(replace_node):
        old_dom = replace_node
    elif old_vnode:
        old_dom = old_vnode._dom
    else:
        old_dom = first_child

    begin_batch()
    try:
        diff(
            parent_dom,
            vnode,
            old_vnode or EMPTY_VNODE,
            EMPTY_OBJ,
            getattr(parent_dom, "namespaceURI", None),
            excess,
            commit_queue,
            old_dom,
            is_hydrating,
            ref_queue,
        )

        commit_root(commit_queue, vnode, ref_queue)

        vnode.props["children"] = NULL
    finally:
        # Preact lets the microtask queue drain here; the port flushes any
        # ``setState`` scheduled during mount (e.g. from ``componentDidMount``).
        end_batch()


def hydrate(vnode, parent_dom):
    render(vnode, parent_dom, hydrate)

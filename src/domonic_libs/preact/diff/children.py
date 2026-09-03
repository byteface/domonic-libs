# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/diff/children.js.
"""``diff_children`` and the skew-based keyed reconciliation of a child list.

``construct_new_children_array`` normalises the render result (strings/numbers to
text vnodes, nested lists to keyless Fragments, re-used vnodes to clones),
matches each new child to an old one via ``find_matching_index`` and a running
``skew`` offset, and marks nodes ``INSERT_VNODE`` when they must physically move.
``diff_children`` then diffs each pair and threads ``old_dom`` through as the
insertion anchor.
"""

from __future__ import annotations

from ..constants import EMPTY_ARR, INSERT_VNODE, MATCHED, NULL, UNDEFINED
from ..create_element import Fragment, VNode, create_vnode
from ..util import is_array


def diff_children(
    parent_dom,
    render_result,
    new_parent_vnode,
    old_parent_vnode,
    global_context,
    namespace,
    excess_dom_children,
    commit_queue,
    old_dom,
    is_hydrating,
    ref_queue,
):
    from ..create_element import EMPTY_VNODE
    from .index import apply_ref, diff

    old_children = (
        old_parent_vnode._children
        if (old_parent_vnode and old_parent_vnode._children)
        else EMPTY_ARR
    )

    new_children_length = len(render_result)

    old_dom = _construct_new_children_array(
        new_parent_vnode, render_result, old_children, old_dom, new_children_length
    )

    first_child_dom = NULL

    for i in range(new_children_length):
        child_vnode = new_parent_vnode._children[i]
        if child_vnode is NULL:
            continue

        old_vnode = NULL
        if child_vnode._index != -1 and child_vnode._index < len(old_children):
            old_vnode = old_children[child_vnode._index]
        if not old_vnode:
            old_vnode = EMPTY_VNODE

        child_vnode._index = i

        result = diff(
            parent_dom,
            child_vnode,
            old_vnode,
            global_context,
            namespace,
            excess_dom_children,
            commit_queue,
            old_dom,
            is_hydrating,
            ref_queue,
        )

        new_dom = child_vnode._dom

        if child_vnode.ref and old_vnode.ref is not child_vnode.ref:
            if old_vnode.ref:
                apply_ref(old_vnode.ref, NULL, child_vnode)
            ref_queue.append(child_vnode.ref)
            ref_queue.append(child_vnode._component or new_dom)
            ref_queue.append(child_vnode)

        if first_child_dom is NULL and new_dom is not NULL:
            first_child_dom = new_dom

        if child_vnode._flags & INSERT_VNODE:
            old_dom = _insert(child_vnode, old_dom, parent_dom)
            if old_vnode._dom:
                old_vnode._dom = NULL
        elif callable(child_vnode.type) and result is not UNDEFINED:
            old_dom = result
        elif new_dom:
            old_dom = new_dom.nextSibling

        child_vnode._flags &= ~(INSERT_VNODE | MATCHED)

    new_parent_vnode._dom = first_child_dom

    return old_dom


def _construct_new_children_array(
    new_parent_vnode, render_result, old_children, old_dom, new_children_length
):
    from ..component import get_dom_sibling
    from .index import unmount

    old_children_length = len(old_children)
    remaining_old_children = old_children_length
    skew = 0

    new_parent_vnode._children = [NULL] * new_children_length

    for i in range(new_children_length):
        child_vnode = render_result[i]

        if child_vnode is NULL or isinstance(child_vnode, bool) or callable(child_vnode):
            new_parent_vnode._children[i] = NULL
            continue
        elif isinstance(child_vnode, (str, int, float)) and not isinstance(
            child_vnode, bool
        ):
            child_vnode = new_parent_vnode._children[i] = create_vnode(
                NULL, child_vnode, NULL, NULL, NULL
            )
        elif is_array(child_vnode):
            child_vnode = new_parent_vnode._children[i] = create_vnode(
                Fragment, {"children": child_vnode}, NULL, NULL, NULL
            )
        elif isinstance(child_vnode, VNode) and child_vnode._depth > 0:
            # VNode already in use -- clone it.
            child_vnode = new_parent_vnode._children[i] = create_vnode(
                child_vnode.type,
                child_vnode.props,
                child_vnode.key,
                child_vnode.ref if child_vnode.ref else NULL,
                child_vnode._original,
            )
        else:
            new_parent_vnode._children[i] = child_vnode

        skewed_index = i + skew
        child_vnode._parent = new_parent_vnode
        child_vnode._depth = new_parent_vnode._depth + 1

        matching_index = child_vnode._index = _find_matching_index(
            child_vnode, old_children, skewed_index, remaining_old_children
        )

        old_vnode = NULL
        if matching_index != -1:
            # JS reads ``oldChildren[matchingIndex]`` which yields ``undefined``
            # (not an error) when the index is past the end of an empty list.
            if matching_index < len(old_children):
                old_vnode = old_children[matching_index]
            remaining_old_children -= 1
            if old_vnode:
                old_vnode._flags |= MATCHED

        is_mounting = old_vnode is NULL or old_vnode._original is NULL

        if is_mounting:
            if matching_index == -1:
                if new_children_length > old_children_length:
                    skew -= 1
                elif new_children_length < old_children_length:
                    skew += 1
            if not callable(child_vnode.type):
                child_vnode._flags |= INSERT_VNODE
        elif matching_index != skewed_index:
            if matching_index == skewed_index - 1:
                skew -= 1
            elif matching_index == skewed_index + 1:
                skew += 1
            else:
                if matching_index > skewed_index:
                    skew -= 1
                else:
                    skew += 1
                child_vnode._flags |= INSERT_VNODE

    if remaining_old_children:
        for i in range(old_children_length):
            old_vnode = old_children[i]
            if old_vnode is not NULL and (old_vnode._flags & MATCHED) == 0:
                if old_vnode._dom is old_dom:
                    old_dom = get_dom_sibling(old_vnode)
                unmount(old_vnode, old_vnode)

    return old_dom


def _insert(parent_vnode, old_dom, parent_dom):
    if callable(parent_vnode.type):
        children = parent_vnode._children
        i = 0
        while children and i < len(children):
            if children[i]:
                children[i]._parent = parent_vnode
                old_dom = _insert(children[i], old_dom, parent_dom)
            i += 1
        return old_dom
    elif parent_vnode._dom is not old_dom:
        if old_dom and parent_vnode.type and getattr(old_dom, "parentNode", None) is None:
            old_dom = get_dom_sibling_stub(parent_vnode)
        old_dom = parent_dom.insertBefore(parent_vnode._dom, old_dom or NULL)

    while True:
        old_dom = old_dom and old_dom.nextSibling
        if old_dom is NULL or getattr(old_dom, "nodeType", None) != 8:
            break

    return old_dom


def get_dom_sibling_stub(parent_vnode):
    from ..component import get_dom_sibling

    return get_dom_sibling(parent_vnode)


def to_child_array(children, out=None):
    if out is None:
        out = []
    if children is NULL or isinstance(children, bool):
        pass
    elif is_array(children):
        for child in children:
            to_child_array(child, out)
    else:
        out.append(children)
    return out


def _find_matching_index(child_vnode, old_children, skewed_index, remaining_old_children):
    key = child_vnode.key
    type_ = child_vnode.type
    old_vnode = old_children[skewed_index] if 0 <= skewed_index < len(old_children) else NULL
    matched = old_vnode is not NULL and (old_vnode._flags & MATCHED) == 0

    should_search = remaining_old_children > (1 if matched else 0)

    if (old_vnode is NULL and key is None) or (
        matched and key == old_vnode.key and type_ == old_vnode.type
    ):
        return skewed_index
    elif should_search:
        x = skewed_index - 1
        y = skewed_index + 1
        while x >= 0 or y < len(old_children):
            if x >= 0:
                child_index = x
                x -= 1
            else:
                child_index = y
                y += 1
            if not (0 <= child_index < len(old_children)):
                continue
            old_vnode = old_children[child_index]
            if (
                old_vnode is not NULL
                and (old_vnode._flags & MATCHED) == 0
                and key == old_vnode.key
                and type_ == old_vnode.type
            ):
                return child_index

    return -1


# Public alias.
toChildArray = to_child_array

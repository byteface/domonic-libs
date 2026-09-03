# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/diff/index.js.
"""The reconciler core: ``diff``, ``diff_element_nodes``, ``commit_root``,
``unmount`` and ``apply_ref``.

``diff`` dispatches on the vnode type: a callable is a component (class or
function), otherwise it is a host element (or, for ``type is None``, a text
node). Preact's ``outer:`` labelled break -- taken when
``shouldComponentUpdate`` bails -- is modelled with a one-shot ``for`` loop.
"""

from __future__ import annotations

import inspect

from domonic.dom import document

from ..constants import (
    EMPTY_OBJ,
    MATH_NAMESPACE,
    MODE_HYDRATE,
    MODE_SUSPENDED,
    NULL,
    RESET_MODE,
    SVG_NAMESPACE,
    UNDEFINED,
    XHTML_NAMESPACE,
)
from ..create_element import Fragment, VNode, clone_vnode
from ..options import options
from ..util import assign, is_array, remove_node
from .props import set_property


def diff(
    parent_dom,
    new_vnode,
    old_vnode,
    global_context,
    namespace,
    excess_dom_children,
    commit_queue,
    old_dom,
    is_hydrating,
    ref_queue,
):
    from ..component import BaseComponent, get_dom_sibling
    from .children import diff_children

    new_type = new_vnode.type

    # Guards against JSON-injection: a plain object masquerading as a vnode.
    if not isinstance(new_vnode, VNode):
        return NULL

    # If the previous diff bailed out, resume creating/hydrating.
    if old_vnode._flags & MODE_SUSPENDED:
        is_hydrating = bool(old_vnode._flags & MODE_HYDRATE)
        old_dom = new_vnode._dom = old_vnode._dom
        excess_dom_children = [old_dom]

    if options._diff:
        options._diff(new_vnode)

    for _once in (0,):
        if callable(new_type):
            old_commit_queue_length = len(commit_queue)
            try:
                new_props = new_vnode.props
                is_class_component = isinstance(new_type, type) and issubclass(
                    new_type, BaseComponent
                )

                # createContext support: contextType pulls the provider value.
                ctx_type = getattr(new_type, "contextType", None)
                provider = (
                    global_context.get(ctx_type._id) if ctx_type else None
                )
                if ctx_type:
                    component_context = (
                        provider.props["value"] if provider else ctx_type._defaultValue
                    )
                else:
                    component_context = global_context

                is_new = False
                if old_vnode._component:
                    c = new_vnode._component = old_vnode._component
                    clear_processing_exception = c._processingException = c._pendingError
                else:
                    if is_class_component:
                        new_vnode._component = c = new_type(new_props, component_context)
                    else:
                        new_vnode._component = c = BaseComponent(
                            new_props, component_context
                        )
                        c._render_fn = new_type
                        c.render = _make_pfc_render(c, new_type)
                    if provider:
                        provider.sub(c)
                    if not c.state:
                        c.state = {}
                    c._globalContext = global_context
                    is_new = c._dirty = True
                    c._renderCallbacks = []
                    c._stateCallbacks = []
                    clear_processing_exception = None

                # getDerivedStateFromProps.
                if is_class_component and c._nextState is NULL:
                    c._nextState = c.state

                gdsfp = getattr(new_type, "getDerivedStateFromProps", None)
                if is_class_component and gdsfp is not None:
                    if c._nextState is c.state:
                        c._nextState = assign({}, dict(c._nextState))
                    assign(c._nextState, gdsfp(new_props, c._nextState) or {})

                old_props = c.props
                old_state = c.state
                c._vnode = new_vnode
                snapshot = None

                if is_new:
                    if (
                        is_class_component
                        and gdsfp is None
                        and getattr(c, "componentWillMount", None) is not None
                    ):
                        c.componentWillMount()
                    if (
                        is_class_component
                        and getattr(c, "componentDidMount", None) is not None
                    ):
                        c._renderCallbacks.append(c.componentDidMount)
                else:
                    cwrp = getattr(c, "componentWillReceiveProps", None)
                    if (
                        is_class_component
                        and gdsfp is None
                        and new_props is not old_props
                        and cwrp is not None
                    ):
                        cwrp(new_props, component_context)

                    scu = getattr(c, "shouldComponentUpdate", None)
                    if new_vnode._original == old_vnode._original or (
                        not c._force
                        and scu is not None
                        and scu(new_props, c._nextState, component_context) is False
                    ):
                        if new_vnode._original != old_vnode._original:
                            c.props = new_props
                            c.state = c._nextState
                            c._dirty = False

                        new_vnode._dom = old_vnode._dom
                        new_vnode._children = old_vnode._children
                        for vn in list(new_vnode._children):
                            if vn:
                                vn._parent = new_vnode

                        c._renderCallbacks.extend(c._stateCallbacks)
                        c._stateCallbacks = []
                        if c._renderCallbacks:
                            commit_queue.append(c)

                        old_dom = get_dom_sibling(old_vnode)
                        break  # == "break outer"

                    cwu = getattr(c, "componentWillUpdate", None)
                    if cwu is not None:
                        cwu(new_props, c._nextState, component_context)

                    cdu = getattr(c, "componentDidUpdate", None)
                    if is_class_component and cdu is not None:
                        _cap_old_props, _cap_old_state = old_props, old_state
                        c._renderCallbacks.append(
                            lambda op=_cap_old_props, os=_cap_old_state: c.componentDidUpdate(
                                op, os, snapshot
                            )
                        )

                c.context = component_context
                c.props = new_props
                c._parentDom = parent_dom
                c._force = False

                render_hook = options._render

                if is_class_component:
                    c.state = c._nextState
                    c._dirty = False
                    if render_hook:
                        render_hook(new_vnode)
                    tmp = c.render(c.props, c.state, c.context)
                    c._renderCallbacks.extend(c._stateCallbacks)
                    c._stateCallbacks = []
                else:
                    count = 0
                    while True:
                        c._dirty = False
                        if render_hook:
                            render_hook(new_vnode)
                        tmp = c.render(c.props, c.state, c.context)
                        c.state = c._nextState
                        count += 1
                        if not c._dirty or count >= 25:
                            break

                c.state = c._nextState

                gcc = getattr(c, "getChildContext", None)
                if gcc is not None:
                    global_context = assign(assign({}, dict(global_context)), gcc())

                gsbu = getattr(c, "getSnapshotBeforeUpdate", None)
                if is_class_component and not is_new and gsbu is not None:
                    snapshot = gsbu(old_props, old_state)

                if (
                    tmp is not NULL
                    and isinstance(tmp, VNode)
                    and tmp.type is Fragment
                    and tmp.key is NULL
                ):
                    render_result = _clone_node(tmp.props["children"])
                else:
                    render_result = tmp

                old_dom = diff_children(
                    parent_dom,
                    render_result if is_array(render_result) else [render_result],
                    new_vnode,
                    old_vnode,
                    global_context,
                    namespace,
                    excess_dom_children,
                    commit_queue,
                    old_dom,
                    is_hydrating,
                    ref_queue,
                )

                c.base = new_vnode._dom

                # Successful render -- clear any stored hydration/bailout state.
                new_vnode._flags &= RESET_MODE

                if c._renderCallbacks:
                    commit_queue.append(c)

                if clear_processing_exception:
                    c._pendingError = c._processingException = NULL

            except Exception as e:  # noqa: BLE001 - error boundary dispatch
                del commit_queue[old_commit_queue_length:]
                new_vnode._original = NULL
                if is_hydrating or excess_dom_children is not NULL:
                    if excess_dom_children is not NULL:
                        for i in range(len(excess_dom_children) - 1, -1, -1):
                            remove_node(excess_dom_children[i])
                else:
                    new_vnode._dom = old_vnode._dom
                if new_vnode._children is NULL:
                    new_vnode._children = old_vnode._children or []
                _mark_as_force(new_vnode)
                options._catchError(e, new_vnode, old_vnode)

        elif excess_dom_children is NULL and new_vnode._original == old_vnode._original:
            new_vnode._children = old_vnode._children
            new_vnode._dom = old_vnode._dom
        else:
            old_dom = new_vnode._dom = _diff_element_nodes(
                old_vnode._dom,
                new_vnode,
                old_vnode,
                global_context,
                namespace,
                excess_dom_children,
                commit_queue,
                is_hydrating,
                ref_queue,
            )

    if options.diffed:
        options.diffed(new_vnode)

    return UNDEFINED if new_vnode._flags & MODE_SUSPENDED else old_dom


def _make_pfc_render(component, fn):
    # A context ``Provider`` component needs the backing instance (Preact's
    # ``this``). Otherwise pass the legacy ``context`` 2nd arg only if the
    # function actually declares it -- most function components take just props,
    # and Python (unlike JS) rejects surplus positional args.
    if getattr(fn, "_preact_context_component", False):
        return lambda props, state, context: fn(component, props)

    try:
        params = list(inspect.signature(fn).parameters.values())
        positional = [
            p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        accepts_context = len(positional) >= 2 or any(
            p.kind == p.VAR_POSITIONAL for p in params
        )
    except (ValueError, TypeError):
        accepts_context = True

    if accepts_context:
        return lambda props, state, context: fn(props, context)
    return lambda props, state, context: fn(props)


def _mark_as_force(vnode):
    if vnode:
        if vnode._component:
            vnode._component._force = True
        if vnode._children:
            for child in vnode._children:
                _mark_as_force(child)


def commit_root(commit_queue, root, ref_queue):
    i = 0
    while i < len(ref_queue):
        apply_ref(ref_queue[i], ref_queue[i + 1], ref_queue[i + 2])
        i += 3

    if options._commit:
        options._commit(root, commit_queue)

    for c in list(commit_queue):
        try:
            callbacks = c._renderCallbacks
            c._renderCallbacks = []
            for cb in list(callbacks):
                cb()
        except Exception as e:  # noqa: BLE001
            options._catchError(e, c._vnode)


def _clone_node(node):
    if not isinstance(node, (VNode, list)) or node is NULL:
        return node
    if isinstance(node, VNode) and node._depth > 0:
        return node
    if is_array(node):
        return [_clone_node(n) for n in node]
    if not isinstance(node, VNode):
        return None
    return clone_vnode(node)


def _diff_element_nodes(
    dom,
    new_vnode,
    old_vnode,
    global_context,
    namespace,
    excess_dom_children,
    commit_queue,
    is_hydrating,
    ref_queue,
):
    from ..component import get_dom_sibling
    from .children import diff_children

    old_props = old_vnode.props or EMPTY_OBJ
    new_props = new_vnode.props
    node_type = new_vnode.type
    new_html = None
    old_html = None
    new_children = None
    input_value = UNDEFINED
    checked = UNDEFINED

    if node_type == "svg":
        namespace = SVG_NAMESPACE
    elif node_type == "math":
        namespace = MATH_NAMESPACE
    elif not namespace:
        namespace = XHTML_NAMESPACE

    if excess_dom_children is not NULL:
        for i in range(len(excess_dom_children)):
            value = excess_dom_children[i]
            if (
                value is not None
                and (hasattr(value, "setAttribute") == bool(node_type))
                and (
                    getattr(value, "localName", None) == node_type
                    if node_type
                    else getattr(value, "nodeType", None) == 3
                )
            ):
                dom = value
                excess_dom_children[i] = NULL
                break

    if dom is NULL:
        if node_type is NULL:
            return document.createTextNode(str(new_props))
        dom = document.createElementNS(
            namespace, node_type, new_props if new_props.get("is") else None
        )
        if is_hydrating:
            if options._hydrationMismatch:
                options._hydrationMismatch(new_vnode, excess_dom_children)
            is_hydrating = False
        excess_dom_children = NULL

    if node_type is NULL:
        if old_props is not new_props and (
            not is_hydrating or getattr(dom, "data", None) != str(new_props)
        ):
            dom.data = str(new_props)
    else:
        if excess_dom_children is not NULL:
            if node_type == "textarea" and new_props.get("defaultValue") is not None:
                excess_dom_children = NULL
            else:
                excess_dom_children = list(dom.childNodes)

        if not is_hydrating and excess_dom_children is not NULL:
            old_props = {}
            try:
                for attr in dom.attributes:
                    old_props[attr.name] = attr.value
            except Exception:  # noqa: BLE001 - domonic NamedNodeMap iteration is quirky
                old_props = {}

        for i in list(old_props):
            value = old_props[i]
            if i == "dangerouslySetInnerHTML":
                old_html = value
            elif (
                i != "children"
                and i not in new_props
                and not (i == "value" and "defaultValue" in new_props)
                and not (i == "checked" and "defaultChecked" in new_props)
            ):
                set_property(dom, i, NULL, value, namespace)

        for i in list(new_props):
            value = new_props[i]
            if i == "children":
                new_children = value
            elif i == "dangerouslySetInnerHTML":
                new_html = value
            elif i == "value":
                input_value = value
            elif i == "checked":
                checked = value
            elif (not is_hydrating or callable(value)) and old_props.get(i) is not value:
                set_property(dom, i, value, old_props.get(i), namespace)

        if new_html:
            if not is_hydrating and (
                not old_html
                or (
                    new_html.get("__html") != old_html.get("__html")
                    and new_html.get("__html") != getattr(dom, "innerHTML", None)
                )
            ):
                dom.innerHTML = new_html.get("__html")
            new_vnode._children = []
        else:
            if old_html:
                dom.innerHTML = ""

            diff_children(
                dom.content if node_type == "template" else dom,
                new_children if is_array(new_children) else [new_children],
                new_vnode,
                old_vnode,
                global_context,
                XHTML_NAMESPACE if node_type == "foreignObject" else namespace,
                excess_dom_children,
                commit_queue,
                (
                    excess_dom_children[0]
                    if excess_dom_children
                    else (
                        get_dom_sibling(old_vnode, 0) if old_vnode._children else NULL
                    )
                ),
                is_hydrating,
                ref_queue,
            )

            if excess_dom_children is not NULL:
                for i in range(len(excess_dom_children) - 1, -1, -1):
                    remove_node(excess_dom_children[i])

        if not is_hydrating or node_type == "textarea":
            if node_type == "progress" and input_value is NULL:
                dom.removeAttribute("value")
            elif input_value is not UNDEFINED and (
                input_value != getattr(dom, "value", UNDEFINED)
                or (node_type == "progress" and not input_value)
                or (node_type == "option" and input_value != old_props.get("value"))
            ):
                set_property(dom, "value", input_value, old_props.get("value"), namespace)

            if checked is not UNDEFINED and checked != getattr(dom, "checked", UNDEFINED):
                set_property(dom, "checked", checked, old_props.get("checked"), namespace)

    return dom


def apply_ref(ref, value, vnode):
    try:
        if callable(ref):
            has_ref_unmount = callable(getattr(ref, "_unmount", None))
            if has_ref_unmount:
                ref._unmount()
            if not has_ref_unmount or value is not NULL:
                try:
                    ref._unmount = ref(value)
                except AttributeError:
                    ref(value)
        else:
            ref["current"] = value
    except Exception as e:  # noqa: BLE001
        options._catchError(e, vnode)


def unmount(vnode, parent_vnode, skip_remove=False):
    if options.unmount:
        options.unmount(vnode)

    ref = vnode.ref
    if ref:
        current = ref.get("current") if isinstance(ref, dict) else None
        if not current or current is vnode._dom:
            apply_ref(ref, NULL, parent_vnode)

    r = vnode._component
    if r is not NULL:
        cwu = getattr(r, "componentWillUnmount", None)
        if cwu:
            try:
                cwu()
            except Exception as e:  # noqa: BLE001
                options._catchError(e, parent_vnode)
        r.base = r._parentDom = r._globalContext = NULL

    children = vnode._children
    if children:
        for child in children:
            if child:
                unmount(child, parent_vnode, skip_remove or not callable(vnode.type))

    if not skip_remove:
        remove_node(vnode._dom)

    vnode._component = vnode._parent = vnode._dom = UNDEFINED

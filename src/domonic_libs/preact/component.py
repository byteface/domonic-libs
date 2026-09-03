# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/component.js.
"""``Component`` base class plus the synchronous rerender queue.

Preact defers rerenders to a microtask (``Promise.resolve().then``). Python has
no ambient event loop here, so ``_defer`` runs the flush synchronously by
default; set ``options.debounceRendering`` (or replace
``component._defer``) to batch. ``setState`` / ``forceUpdate`` therefore trigger
a synchronous re-render unless a debounce is installed.
"""

from __future__ import annotations

from .constants import MODE_HYDRATE, NULL
from .create_element import Fragment, clone_vnode
from .options import options
from .util import assign


class BaseComponent:
    """Base class providing ``setState`` and ``forceUpdate``."""

    def __init__(self, props, context=None):
        self.props = props
        self.context = context
        self.state = getattr(self, "state", None)
        self._vnode = NULL
        self._nextState = NULL
        self._dirty = False
        self._force = False
        self._renderCallbacks = []
        self._stateCallbacks = []
        self._globalContext = NULL
        self._parentDom = NULL
        self._pendingError = NULL
        self._processingException = NULL
        self.base = NULL

    def setState(self, update, callback=None):
        # Only clone state when copying to nextState the first time.
        if self._nextState is not NULL and self._nextState is not self.state:
            s = self._nextState
        else:
            s = self._nextState = assign({}, dict(self.state or {}))

        if callable(update):
            update = update(assign({}, dict(s)), self.props)

        if update:
            assign(s, update)

        # Skip update if updater function returned null.
        if update is NULL:
            return

        if self._vnode:
            if callback:
                self._stateCallbacks.append(callback)
            enqueue_render(self)

    def forceUpdate(self, callback=None):
        if self._vnode:
            # forceUpdate must never call shouldComponentUpdate.
            self._force = True
            if callback:
                self._renderCallbacks.append(callback)
            enqueue_render(self)

    def render(self, props, state, context):
        # BaseComponent.prototype.render = Fragment
        return Fragment(props)


def get_dom_sibling(vnode, child_index=None):
    if child_index is None:
        # Signal to resume the search from the vnode's next sibling.
        return (
            get_dom_sibling(vnode._parent, vnode._index + 1) if vnode._parent else NULL
        )

    while child_index < len(vnode._children):
        sibling = vnode._children[child_index]
        if sibling is not NULL and sibling._dom is not NULL:
            return sibling._dom
        child_index += 1

    # No DOM node found among the children -- climb only if this is a component.
    return get_dom_sibling(vnode) if callable(vnode.type) else NULL


def _render_component(component):
    from .diff.index import commit_root, diff

    if component._parentDom and component._dirty:
        old_vnode = component._vnode
        old_dom = old_vnode._dom
        commit_queue = []
        ref_queue = []
        new_vnode = clone_vnode(old_vnode)
        new_vnode._original = old_vnode._original + 1
        if options.vnode:
            options.vnode(new_vnode)

        diff(
            component._parentDom,
            new_vnode,
            old_vnode,
            component._globalContext,
            component._parentDom.namespaceURI,
            [old_dom] if old_vnode._flags & MODE_HYDRATE else NULL,
            commit_queue,
            get_dom_sibling(old_vnode) if old_dom is NULL else old_dom,
            bool(old_vnode._flags & MODE_HYDRATE),
            ref_queue,
        )

        new_vnode._original = old_vnode._original
        new_vnode._parent._children[new_vnode._index] = new_vnode
        commit_root(commit_queue, new_vnode, ref_queue)
        old_vnode._dom = old_vnode._parent = NULL

        if new_vnode._dom is not old_dom:
            _update_parent_dom_pointers(new_vnode)


def _update_parent_dom_pointers(vnode):
    vnode = vnode._parent
    if vnode is not NULL and vnode._component is not NULL:
        vnode._dom = vnode._component.base = NULL
        for child in list(vnode._children):
            if child is not NULL and child._dom is not NULL:
                vnode._dom = vnode._component.base = child._dom
                break
        return _update_parent_dom_pointers(vnode)


_rerender_queue = []
_prev_debounce = None
_flush_pending = False
_batch_depth = 0


def begin_batch():
    global _batch_depth
    _batch_depth += 1


def end_batch():
    global _batch_depth
    _batch_depth -= 1
    if _batch_depth <= 0:
        _batch_depth = 0
        flush_rerender_queue()


def _defer(callback):
    # Preact defers to a microtask; the port instead marks the queue dirty and
    # relies on ``flush_rerender_queue()`` being called once the current
    # synchronous unit of work (a top-level ``render`` or an event handler)
    # returns. This keeps ``setState`` from re-entering the reconciler mid-diff,
    # which ``catch_error`` depends on (it reads ``component._dirty`` right after
    # invoking ``componentDidCatch``). A ``setState`` / ``forceUpdate`` made
    # outside any batch (e.g. straight from user code) is flushed immediately.
    global _flush_pending
    _flush_pending = True
    if _batch_depth == 0:
        flush_rerender_queue()


def flush_rerender_queue():
    global _flush_pending
    if _flush_pending:
        _flush_pending = False
        _process()


def enqueue_render(c):
    global _prev_debounce
    schedule = False
    if not c._dirty:
        c._dirty = True
        _rerender_queue.append(c)
        was_first = _process._rerender_count == 0
        _process._rerender_count += 1
        if was_first:
            schedule = True
    if not schedule and _prev_debounce != options.debounceRendering:
        schedule = True
    if schedule:
        _prev_debounce = options.debounceRendering
        (_prev_debounce or _defer)(_process)


def _process():
    global _batch_depth
    _batch_depth += 1
    try:
        length = 1
        while _rerender_queue:
            if len(_rerender_queue) > length:
                _rerender_queue.sort(key=lambda c: c._vnode._depth)
            c = _rerender_queue.pop(0)
            length = len(_rerender_queue)
            _render_component(c)
    finally:
        _rerender_queue.clear()
        _process._rerender_count = 0
        _batch_depth -= 1
        if _batch_depth < 0:
            _batch_depth = 0


_process._rerender_count = 0

# Public aliases.
Component = BaseComponent
getDomSibling = get_dom_sibling
enqueueRender = enqueue_render

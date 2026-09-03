# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors hooks/src/index.js.
"""``preact/hooks`` -- ``useState``, ``useReducer``, ``useEffect``,
``useLayoutEffect``, ``useRef``, ``useMemo``, ``useCallback``, ``useContext``,
``useImperativeHandle``, ``useErrorBoundary``, ``useId``, ``useDebugValue``.

Importing this module rewires the shared ``options`` hooks (exactly like
importing ``preact/hooks`` in JS). Two behavioural notes for the server-side
port:

* There is no paint, so *passive* effects (``useEffect``) are flushed
  synchronously at the end of ``options._commit`` rather than on the next
  animation frame. Cleanup/run ordering within a commit is preserved; only the
  "after paint" delay is gone.
* ``argsChanged`` compares dependencies with ``!=`` (value equality) rather than
  JS ``!==`` (identity). Passing a fresh list/dict literal as a dependency on
  every render -- already a bug in JS -- will therefore *not* re-fire the effect.
"""

from __future__ import annotations

from .options import options

_current_index = 0
_current_component = None
_previous_component = None
_current_hook = 0
_after_paint_effects = []


class _HookState:
    __slots__ = (
        "_value",
        "_nextValue",
        "_pendingArgs",
        "_args",
        "_component",
        "_reducer",
        "_cleanup",
        "_factory",
        "_context",
    )

    def __init__(self):
        self._value = None
        self._nextValue = None
        self._pendingArgs = None
        self._args = None
        self._component = None
        self._reducer = None
        self._cleanup = None
        self._factory = None
        self._context = None


_old_before_diff = options._diff
_old_before_render = options._render
_old_after_diff = options.diffed
_old_commit = options._commit
_old_before_unmount = options.unmount
_old_root = options._root


def _options_diff(vnode):
    global _current_component
    _current_component = None
    if _old_before_diff:
        _old_before_diff(vnode)


def _options_root(vnode, parent_dom):
    pc = getattr(parent_dom, "_children", None)
    if vnode and pc is not None and getattr(pc, "_mask", None):
        vnode._mask = pc._mask
    if _old_root:
        _old_root(vnode, parent_dom)


def _options_render(vnode):
    global _current_component, _current_index, _previous_component
    if _old_before_render:
        _old_before_render(vnode)

    _current_component = vnode._component
    _current_index = 0

    hooks = getattr(_current_component, "_hooks", None)
    if hooks:
        if _previous_component is _current_component:
            hooks["_pendingEffects"] = []
            _current_component._renderCallbacks = []
            for hook_item in list(hooks["_list"]):
                if hook_item._nextValue:
                    hook_item._value = hook_item._nextValue
                hook_item._pendingArgs = None
                hook_item._nextValue = None
        else:
            for h in list(hooks["_pendingEffects"]):
                _invoke_cleanup(h)
            for h in list(hooks["_pendingEffects"]):
                _invoke_effect(h)
            hooks["_pendingEffects"] = []
            _current_index = 0
    _previous_component = _current_component


def _options_diffed(vnode):
    global _previous_component, _current_component
    if _old_after_diff:
        _old_after_diff(vnode)

    c = vnode._component
    if c and getattr(c, "_hooks", None):
        if c._hooks["_pendingEffects"]:
            _after_paint_effects.append(c)
        for hook_item in list(c._hooks["_list"]):
            if hook_item._pendingArgs is not None:
                hook_item._args = hook_item._pendingArgs
                hook_item._pendingArgs = None
    _previous_component = _current_component = None


def _options_commit(vnode, commit_queue):
    def process(component):
        try:
            for h in list(component._renderCallbacks):
                _invoke_cleanup(h)
            kept = []
            for cb in list(component._renderCallbacks):
                if getattr(cb, "_value", None):
                    if _invoke_effect(cb):
                        kept.append(cb)
                else:
                    kept.append(cb)
            component._renderCallbacks = kept
        except Exception as e:  # noqa: BLE001
            for c in commit_queue:
                if getattr(c, "_renderCallbacks", None):
                    c._renderCallbacks = []
            options._catchError(e, component._vnode)

    for component in list(commit_queue):
        process(component)

    if _old_commit:
        _old_commit(vnode, commit_queue)

    # Server-side port: no paint to wait for -- flush passive effects now.
    _flush_after_paint_effects()


def _options_unmount(vnode):
    if _old_before_unmount:
        _old_before_unmount(vnode)

    c = vnode._component
    if c and getattr(c, "_hooks", None):
        has_errored = None
        for s in list(c._hooks["_list"]):
            try:
                _invoke_cleanup(s)
            except Exception as e:  # noqa: BLE001
                has_errored = e
        c._hooks = None
        if has_errored is not None:
            options._catchError(has_errored, c._vnode)


options._diff = _options_diff
options._root = _options_root
options._render = _options_render
options.diffed = _options_diffed
options._commit = _options_commit
options.unmount = _options_unmount


def _next_index():
    global _current_index
    i = _current_index
    _current_index += 1
    return i


def _get_hook_state(index, hook_type):
    global _current_hook
    if options._hook:
        options._hook(_current_component, index, _current_hook or hook_type)
    _current_hook = 0

    hooks = getattr(_current_component, "_hooks", None)
    if hooks is None:
        hooks = {"_list": [], "_pendingEffects": []}
        _current_component._hooks = hooks

    if index >= len(hooks["_list"]):
        hooks["_list"].append(_HookState())

    return hooks["_list"][index]


def use_state(initial_state=None):
    global _current_hook
    _current_hook = 1
    return use_reducer(_invoke_or_return, initial_state)


def use_reducer(reducer, initial_state=None, init=None):
    hook_state = _get_hook_state(_next_index(), 2)
    hook_state._reducer = reducer
    if not hook_state._component:
        initial = (
            _invoke_or_return(None, initial_state) if init is None else init(initial_state)
        )

        def dispatch(action, _hs=hook_state):
            current_value = (
                _hs._nextValue[0] if _hs._nextValue else _hs._value[0]
            )
            next_value = _hs._reducer(current_value, action)
            if current_value != next_value:
                _hs._nextValue = [next_value, _hs._value[1]]
                _hs._component.setState({})

        hook_state._value = [initial, dispatch]
        hook_state._component = _current_component

        if not getattr(_current_component, "_hasScuFromHooks", False):
            _current_component._hasScuFromHooks = True
            _install_hook_scu(_current_component, hook_state)

    return hook_state._nextValue or hook_state._value


def _install_hook_scu(comp, hook_state):
    prev_scu = [getattr(comp, "shouldComponentUpdate", None)]
    prev_cwu = getattr(comp, "componentWillUpdate", None)

    def update_hook_state(p, s, c):
        if not getattr(hook_state._component, "_hooks", None):
            return True
        updated_hook = False
        should_update = hook_state._component.props is not p
        for hook_item in list(hook_state._component._hooks["_list"]):
            if hook_item._nextValue:
                updated_hook = True
                current_value = hook_item._value[0]
                hook_item._value = hook_item._nextValue
                hook_item._nextValue = None
                if current_value != hook_item._value[0]:
                    should_update = True
        if prev_scu[0]:
            result = prev_scu[0](p, s, c)
            return (result or should_update) if updated_hook else result
        return (not updated_hook) or should_update

    def component_will_update(p, s, c):
        if comp._force:
            tmp = prev_scu[0]
            prev_scu[0] = None
            update_hook_state(p, s, c)
            prev_scu[0] = tmp
        if prev_cwu:
            prev_cwu(p, s, c)

    comp.componentWillUpdate = component_will_update
    comp.shouldComponentUpdate = update_hook_state


def use_effect(callback, args=None):
    state = _get_hook_state(_next_index(), 3)
    if not options._skipEffects and _args_changed(state._args, args):
        state._value = callback
        state._pendingArgs = args
        _current_component._hooks["_pendingEffects"].append(state)


def use_layout_effect(callback, args=None):
    state = _get_hook_state(_next_index(), 4)
    if not options._skipEffects and _args_changed(state._args, args):
        state._value = callback
        state._pendingArgs = args
        _current_component._renderCallbacks.append(state)


def use_ref(initial_value=None):
    global _current_hook
    _current_hook = 5
    return use_memo(lambda: {"current": initial_value}, [])


def use_imperative_handle(ref, create_handle, args=None):
    global _current_hook
    _current_hook = 6

    def effect():
        if callable(ref):
            result = ref(create_handle())

            def cleanup():
                ref(None)
                if result and callable(result):
                    result()

            return cleanup
        elif ref:
            ref["current"] = create_handle()

            def cleanup():
                ref["current"] = None

            return cleanup

    use_layout_effect(effect, args if args is None else list(args) + [ref])


def use_memo(factory, args=None):
    state = _get_hook_state(_next_index(), 7)
    if _args_changed(state._args, args):
        state._value = factory()
        state._args = args
        state._factory = factory
    return state._value


def use_callback(callback, args=None):
    global _current_hook
    _current_hook = 8
    return use_memo(lambda: callback, args)


def use_context(context):
    ctx = getattr(_current_component, "context", None) or {}
    provider = ctx.get(context._id) if hasattr(ctx, "get") else None
    state = _get_hook_state(_next_index(), 9)
    state._context = context
    if not provider:
        return context._defaultValue
    if state._value is None:
        state._value = True
        provider.sub(_current_component)
    return provider.props["value"]


def use_debug_value(value, formatter=None):
    if options.useDebugValue:
        options.useDebugValue(formatter(value) if formatter else value)


def use_error_boundary(cb=None):
    state = _get_hook_state(_next_index(), 10)
    err_state = use_state(None)
    state._value = cb
    if not getattr(_current_component, "componentDidCatch", None):
        comp = _current_component

        def _did_catch(err, error_info):
            if state._value:
                state._value(err, error_info)
            err_state[1](err)

        comp.componentDidCatch = _did_catch

    return [err_state[0], lambda: err_state[1](None)]


def use_id():
    state = _get_hook_state(_next_index(), 11)
    if not state._value:
        root = _current_component._vnode
        while root is not None and not root._mask and root._parent is not None:
            root = root._parent
        mask = root._mask or [0, 0]
        root._mask = mask
        state._value = "P" + str(mask[0]) + "-" + str(mask[1])
        mask[1] += 1
    return state._value


def _flush_after_paint_effects():
    while _after_paint_effects:
        component = _after_paint_effects.pop(0)
        hooks = getattr(component, "_hooks", None)
        if not component._parentDom or not hooks:
            continue
        try:
            for h in list(hooks["_pendingEffects"]):
                _invoke_cleanup(h)
            for h in list(hooks["_pendingEffects"]):
                _invoke_effect(h)
            hooks["_pendingEffects"] = []
        except Exception as e:  # noqa: BLE001
            hooks["_pendingEffects"] = []
            options._catchError(e, component._vnode)


def _invoke_cleanup(hook):
    global _current_component
    comp = _current_component
    cleanup = getattr(hook, "_cleanup", None)
    if callable(cleanup):
        hook._cleanup = None
        cleanup()
    _current_component = comp


def _invoke_effect(hook):
    global _current_component
    comp = _current_component
    hook._cleanup = hook._value()
    _current_component = comp
    return None


def _args_changed(old_args, new_args):
    if old_args is None:
        return True
    if new_args is None:
        return True
    if len(old_args) != len(new_args):
        return True
    return any(new_args[i] != old_args[i] for i in range(len(new_args)))


def _invoke_or_return(arg, f):
    return f(arg) if callable(f) else f


# Public aliases matching Preact's camelCase names.
useState = use_state
useReducer = use_reducer
useEffect = use_effect
useLayoutEffect = use_layout_effect
useRef = use_ref
useImperativeHandle = use_imperative_handle
useMemo = use_memo
useCallback = use_callback
useContext = use_context
useDebugValue = use_debug_value
useErrorBoundary = use_error_boundary
useId = use_id

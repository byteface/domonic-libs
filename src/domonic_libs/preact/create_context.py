# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/create-context.js.
"""``create_context`` -- ``Provider`` / ``Consumer`` / ``useContext`` plumbing.

Preact's ``Context`` is a function component that reads ``this`` (the backing
component instance). Python functions have no ``this``, so the ``Context``
component here takes the instance as an explicit first argument and the PFC
render shim in ``diff`` passes it when the callable is tagged
``_preact_context_component``.
"""

from __future__ import annotations

from .component import enqueue_render
from .constants import NULL

_i = 0


def create_context(default_value):
    global _i
    context_id = "__cC" + str(_i)
    _i += 1

    def Context(component, props):
        if not getattr(component, "getChildContext", None):
            subs = set()
            ctx = {context_id: component}

            component.getChildContext = lambda: ctx

            def _will_unmount():
                nonlocal subs
                subs = NULL

            component.componentWillUnmount = _will_unmount

            def _scu(_props, *_rest):
                if component.props.get("value") != _props.get("value"):
                    for c in list(subs):
                        c._force = True
                        enqueue_render(c)

            component.shouldComponentUpdate = _scu

            def _sub(c):
                subs.add(c)
                old = getattr(c, "componentWillUnmount", None)

                def _cwu():
                    if subs:
                        subs.discard(c)
                    if old:
                        old()

                c.componentWillUnmount = _cwu

            component.sub = _sub

        return props.get("children")

    Context._preact_context_component = True
    Context._id = context_id
    Context._defaultValue = default_value

    def Consumer(props, context_value):
        return props["children"](context_value)

    Context.Consumer = Consumer
    Context.Provider = Context
    Consumer.contextType = Context

    return Context


createContext = create_context

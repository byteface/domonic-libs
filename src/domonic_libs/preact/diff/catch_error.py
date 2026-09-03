# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/diff/catch-error.js.
"""``catch_error`` -- walk up from a throwing vnode to the nearest error boundary.

A component is an error boundary if its class defines
``get_derived_state_from_error`` (static-ish) or ``component_did_catch``. If none
is found the original error is re-raised.
"""

from __future__ import annotations


def catch_error(error, vnode, old_vnode=None, error_info=None):
    handled = False
    vnode = vnode._parent
    while vnode:
        component = vnode._component
        if component is not None and not getattr(component, "_processingException", None):
            try:
                ctor = component.__class__

                derived = getattr(ctor, "getDerivedStateFromError", None) or getattr(
                    ctor, "get_derived_state_from_error", None
                )
                if derived is not None:
                    component.setState(derived(error))
                    handled = component._dirty

                did_catch = getattr(component, "componentDidCatch", None) or getattr(
                    component, "component_did_catch", None
                )
                if did_catch is not None:
                    did_catch(error, error_info or {})
                    handled = component._dirty

                if handled:
                    component._pendingError = component
                    return component
            except Exception as exc:  # noqa: BLE001 - mirrors JS catch(e){ error = e }
                error = exc
        vnode = vnode._parent

    raise error

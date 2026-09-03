# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/diff/props.js.
"""``set_property`` -- reconcile a single prop onto a real DOM node.

Handles ``style`` (string or dict), ``on*`` event handlers (via a shared proxy
that reads ``dom._listeners``), the "set as IDL property if the node has it,
else set an attribute" rule, and SVG name normalisation.

Three deliberate divergences from Preact, all forced by domonic's server-side
DOM and noted in ``docs/domonic-wrinkles.md``:

* Event names are always lower-cased (``onClick`` -> ``click``). Preact only
  lower-cases when ``('on' + name).toLowerCase() in dom`` -- a feature probe for
  the DOM's ``onclick``-style IDL attributes, which domonic elements do not
  expose, so the probe is always false and the un-lowercased fallback would
  register an un-dispatchable ``"Click"`` listener.
* The event-clock guard for re-entrant dispatch (preact#3927) is dropped; the
  server-side DOM dispatches synchronously with no micro-tick bubbling.
* ``name`` is forced through ``setAttribute`` (added to ``_ATTR_ONLY``): domonic
  exposes a writable ``Element.name`` aliased to the tag name, so assigning it
  as an IDL property renames the element instead of setting the content
  attribute.
"""

from __future__ import annotations

import re

from ..constants import IS_NON_DIMENSIONAL, NULL, SVG_NAMESPACE, UNDEFINED
from ..options import options

_IS_NON_DIMENSIONAL = re.compile(IS_NON_DIMENSIONAL, re.I)
_CAPTURE_REGEX = re.compile(r"(PointerCapture)$|Capture$", re.I)
_EVENT_PROP_RE = re.compile(r"^_?on[A-Za-z]")


def is_event_prop(name):
    """True for ``onClick`` and the domonic ``_onclick`` spelling alike."""
    return isinstance(name, str) and bool(_EVENT_PROP_RE.match(name))

_XLINK_REGEX = re.compile(r"xlink(H|:h)")
_S_NAME_REGEX = re.compile(r"sName$")

# name -> whether the DOM property should be preferred over setAttribute is
# decided by ``hasattr``; this set is Preact's explicit "always use attribute"
# exception list.
#
# ``name`` is a domonic-specific addition (see the module docstring): every
# domonic element exposes a writable ``.name`` bound to its tag name, so the
# ``hasattr`` probe below would pass and ``setattr(dom, "name", value)`` would
# silently rename ``<input name="q">`` to ``<q>``.
_ATTR_ONLY = {
    "width",
    "height",
    "href",
    "list",
    "form",
    "tabIndex",
    "download",
    "rowSpan",
    "colSpan",
    "role",
    "popover",
    "name",
}

_event_clock = 0


def _set_style(style, key, value):
    if key and key[0] == "-":
        style.setProperty(key, "" if value is NULL else value)
    elif value is NULL:
        style[key] = ""
    elif not isinstance(value, (int, float)) or isinstance(value, bool) or _IS_NON_DIMENSIONAL.search(key):
        style[key] = value
    else:
        style[key] = f"{value}px"


def _make_event_proxy(use_capture):
    def proxy(event):
        from ..component import begin_batch, end_batch

        dom = getattr(event, "currentTarget", None) or getattr(event, "target", None)
        listeners = getattr(dom, "_listeners", None)
        if listeners:
            handler = listeners.get(event.type + str(use_capture))
            if handler:
                begin_batch()
                try:
                    return handler(options.event(event) if options.event else event)
                finally:
                    # The handler's synchronous work is done -- run any
                    # ``setState`` it scheduled (Preact's microtask boundary).
                    end_batch()

    return proxy


_event_proxy = _make_event_proxy(False)
_event_proxy_capture = _make_event_proxy(True)


def set_property(dom, name, value, old_value, namespace):
    if name == "style":
        style = dom.style
        if isinstance(value, str):
            style.cssText = value
        else:
            if isinstance(old_value, str):
                style.cssText = ""
                old_value = ""
            if old_value:
                for key in old_value:
                    if not (value and key in value):
                        _set_style(style, key, "")
            if value:
                for key in value:
                    if not old_value or value[key] != old_value.get(key):
                        _set_style(style, key, value[key])

    elif is_event_prop(name):
        raw = name[1:] if name[0] == "_" else name
        use_capture = bool(_CAPTURE_REGEX.search(raw))
        raw = _CAPTURE_REGEX.sub(r"\1", raw)
        # See module docstring: always lower-case for the server-side DOM.
        ev = raw.lower()[2:]

        if isinstance(getattr(dom, "kwargs", None), dict):
            # domonic DOM: register the *raw* handler with addEventListener.
            # domonic's own ``dispatchEvent`` then calls it (standalone / Pyodide
            # use), and a domonic ``App``'s bind pass discovers it via
            # ``node.listeners`` and rewrites ``kwargs['_on<ev>']`` to a client
            # dispatch string. No proxy -- that would double-fire against
            # domonic's ``on<type>`` attribute dispatch -- and nothing that
            # serialises into the markup.
            if old_value and old_value is not value:
                dom.removeEventListener(ev, old_value, use_capture)
            if value and old_value is not value:
                dom.addEventListener(ev, value, use_capture)
        else:
            # Real browser DOM: register via addEventListener behind the proxy.
            listeners = getattr(dom, "_listeners", None)
            if listeners is None:
                listeners = {}
                dom._listeners = listeners
            listeners[ev + str(use_capture)] = value

            proxy = _event_proxy_capture if use_capture else _event_proxy
            if value:
                if not old_value:
                    dom.addEventListener(ev, proxy, use_capture)
            else:
                dom.removeEventListener(ev, proxy, use_capture)

    else:
        if namespace == SVG_NAMESPACE:
            name = _XLINK_REGEX.sub("h", name)
            name = _S_NAME_REGEX.sub("s", name)
        elif name not in _ATTR_ONLY and name != "tabIndex" and _has_property(dom, name):
            try:
                setattr(dom, name, "" if value is NULL else value)
                return
            except Exception:  # noqa: BLE001 - mirrors JS empty catch
                pass

        if callable(value):
            # never serialize functions as attribute values
            pass
        elif value is not NULL and value is not UNDEFINED and (value is not False or name[4:5] == "-"):
            dom.setAttribute(name, "" if (name == "popover" and value is True) else value)
        else:
            dom.removeAttribute(name)


def _has_property(dom, name):
    # Stand-in for JS ``name in dom`` (does the node expose this as a property?).
    return hasattr(dom, name)

# Ported from preactjs/preact (MIT), tag 10.29.8. Preserve the upstream licence
# when redistributing. Mirrors src/index.js (the ``preact`` entry point);
# ``preact/hooks`` is ported as ``domonic_libs.preact.hooks``.
"""A faithful port of Preact -- 3kB React-compatible virtual DOM -- running on
domonic's server-side DOM.

    from domonic_libs.preact import h, render, Component
    from domonic.dom import document

    def App(props):
        return h("h1", None, "Hello ", props["name"])

    root = document.createElement("div")
    render(h(App, {"name": "world"}), root)
    str(root)  # '<div><h1>Hello world</h1></div>'

There is no JSX, so ``h`` / ``createElement`` is the authoring API. Component
lifecycle names keep their upstream camelCase (``componentDidMount``,
``shouldComponentUpdate``, ...). ``setState`` re-renders synchronously unless
``options.debounceRendering`` is installed. See ``docs/domonic-wrinkles.md`` for
the DOM behaviours the port has to work around.
"""

from __future__ import annotations

from .clone_element import clone_element, cloneElement
from .component import Component, BaseComponent, enqueue_render
from .create_context import create_context, createContext
from .create_element import (
    Fragment,
    VNode,
    create_element,
    create_ref,
    createElement,
    createRef,
    h,
    is_valid_element,
    isValidElement,
)
from .diff.children import to_child_array, toChildArray
from .options import options
from .render import hydrate, render

__all__ = [
    "BaseComponent",
    "Component",
    "Fragment",
    "VNode",
    "clone_element",
    "cloneElement",
    "create_context",
    "create_element",
    "create_ref",
    "createContext",
    "createElement",
    "createRef",
    "enqueue_render",
    "h",
    "hydrate",
    "is_valid_element",
    "isValidElement",
    "options",
    "render",
    "to_child_array",
    "toChildArray",
]

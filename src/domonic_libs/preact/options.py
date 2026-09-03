# Ported from preactjs/preact (MIT), tag 10.29.8. Mirrors src/options.js.
"""The ``options`` object -- the renderer's extension points.

Every field is an optional callback that add-ons (here: ``preact/hooks``, ported
as ``domonic_libs.preact.hooks``) may install. Reading an unset hook must be
cheap and falsy, so missing attributes resolve to ``None`` via ``__getattr__``.
The only default is ``_catchError`` (the error-boundary walker).
"""

from __future__ import annotations

from .diff.catch_error import catch_error


class _Options:
    # Hooks read by the reconciler. Declared so ``__getattr__`` only fires for
    # genuinely-unset extension points and typos surface as ``None`` too, exactly
    # like property access on a plain JS object.
    _known = (
        "vnode",
        "diffed",
        "unmount",
        "_root",
        "_diff",
        "_render",
        "_commit",
        "_catchError",
        "_hook",
        "_hydrationMismatch",
        "_skipEffects",
        "event",
        "useDebugValue",
        "debounceRendering",
        "requestAnimationFrame",
    )

    def __getattr__(self, name):
        # Called only when the attribute is not set on the instance.
        return None


options = _Options()
options._catchError = catch_error

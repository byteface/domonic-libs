"""The domonic-libs app framework.

``BaseApp`` (in ``core``) holds the host-agnostic render loop. ``DesktopApp``
(``desktop``) hosts it in a pywebview window; ``BrowserApp`` (``web``) serves it
to an ordinary browser over a small stdlib HTTP server. ``App`` is an alias for
``DesktopApp`` -- the historical default.

The sibling modules ``bridge``, ``client``, ``events``, ``file_drop``, ``menus``
and ``storage`` hold shared internals.
"""

from __future__ import annotations

from .core import BaseApp
from .desktop import DesktopApp
from .events import BROWSER_EVENTS, Event, on
from .web import BrowserApp

App = DesktopApp

__all__ = [
    "App",
    "BaseApp",
    "BrowserApp",
    "DesktopApp",
    "BROWSER_EVENTS",
    "Event",
    "on",
]

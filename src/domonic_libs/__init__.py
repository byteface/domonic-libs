from .dompurify import DOMPurify, createDOMPurify, sanitize
from .readability import Readability
from .turndown import TurndownService, turndown
from . import validator

def _read_version() -> str:
    from pathlib import Path
    f = Path(__file__).resolve().parents[2] / "VERSION"   # repo-root source checkout
    if f.is_file():
        return f.read_text().strip()
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("domonic-libs")
    except PackageNotFoundError:
        return "0+unknown"


__version__ = _read_version()

__all__ = [
    "App",
    "BROWSER_EVENTS",
    "DOMPurify",
    "Event",
    "Readability",
    "TurndownService",
    "__version__",
    "createDOMPurify",
    "on",
    "sanitize",
    "turndown",
    "validator",
]


def __getattr__(name):
    # The app wrapper is optional -- it pulls in pywebview. The ports above are
    # always available; App / Event / on are loaded lazily so that
    # ``import domonic_libs`` and ``domonic_libs.dompurify`` etc. work with only
    # ``domonic`` installed.
    if name in {"App", "BROWSER_EVENTS", "Event", "on"}:
        try:
            if name == "on":
                from .app.events import on

                return on
            from .app import App, BROWSER_EVENTS, Event
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ImportError(
                f"domonic_libs.{name} needs the app wrapper's dependencies. "
                'Install them with:  pip install "domonic-libs[app]"'
            ) from exc

        return {"App": App, "BROWSER_EVENTS": BROWSER_EVENTS, "Event": Event}[name]
    raise AttributeError(name)

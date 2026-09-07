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


_LAZY_EXPORTS = {
    "DOMPurify": (".dompurify", "DOMPurify"),
    "createDOMPurify": (".dompurify", "createDOMPurify"),
    "sanitize": (".dompurify", "sanitize"),
    "Readability": (".readability", "Readability"),
    "TurndownService": (".turndown", "TurndownService"),
    "turndown": (".turndown", "turndown"),
    "validator": (".validator", None),
}


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        from importlib import import_module

        module_name, attr_name = _LAZY_EXPORTS[name]
        module = import_module(module_name, __name__)
        for export_name, (export_module_name, export_attr_name) in _LAZY_EXPORTS.items():
            if export_module_name == module_name and export_attr_name is not None:
                globals()[export_name] = getattr(module, export_attr_name)
        value = module if attr_name is None else globals()[name]
        globals()[name] = value
        return value

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

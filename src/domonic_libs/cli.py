"""``dlx`` -- a command-line front end for the domonic-libs ports.

    dlx mermaid diagram.mmd -o diagram.svg
    dlx mermaid diagram.mmd --open
    echo "# Hi" | dlx md
    dlx html2md page.html
    dlx read https://example.com/article --md
    dlx sanitize dirty.html --profile html
    dlx validate isEmail ada@example.com
    dlx qs parse "user[name]=ada&tags[]=a&tags[]=b"
    dlx dagre graph.txt --rankdir LR -o graph.svg

Every text command reads a file argument, or stdin when the argument is ``-`` or
omitted, and writes to ``--output`` or stdout. Exit status is ``2`` on a usage
error and ``1`` when a check fails (``validate``) or nothing is produced.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import webbrowser
from pathlib import Path

from . import __version__

_PROG = "dlx"


# --------------------------------------------------------------------------
# shared IO helpers
# --------------------------------------------------------------------------


def _read(src: str | None) -> str:
    if src in (None, "-"):
        return sys.stdin.read()
    return Path(src).read_text(encoding="utf-8")


def _write(text: str, dest: str | None) -> None:
    if dest in (None, "-"):
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    else:
        Path(dest).write_text(text, encoding="utf-8")
        print(f"{_PROG}: wrote {dest}", file=sys.stderr)


def _io_args(p: argparse.ArgumentParser, *, input_help: str = "input file ('-' or omitted = stdin)") -> None:
    p.add_argument("input", nargs="?", help=input_help)
    p.add_argument("-o", "--output", metavar="FILE", help="output file ('-' = stdout, the default)")


def _open_in_browser(markup: str, *, wrap_html: bool, title: str) -> None:
    body = markup
    if wrap_html:
        body = (
            f"<!doctype html><meta charset=utf-8><title>{title}</title>"
            "<style>body{margin:0;display:grid;place-items:center;min-height:100vh;"
            "background:#f4f5f3;font-family:system-ui}svg{max-width:96vw;max-height:96vh}</style>"
            f"{markup}"
        )
    tmp = Path(tempfile.mkdtemp(prefix="dlx-")) / ("preview.html" if wrap_html else "preview.svg")
    tmp.write_text(body, encoding="utf-8")
    webbrowser.open(tmp.as_uri())
    print(f"{_PROG}: opened {tmp}", file=sys.stderr)


# --------------------------------------------------------------------------
# mermaid
# --------------------------------------------------------------------------


def _cmd_mermaid(args) -> int:
    from . import mermaid

    if args.list:
        print("supported diagram types:")
        for token, kind in sorted(set(mermaid._DETECTORS.items())):
            print(f"  {kind:<10} ({token})")
        return 0

    text = _read(args.input)
    try:
        if args.type:
            kind = args.type
            mod = __import__(f"domonic_libs.mermaid.{kind}", fromlist=["parse"])
            element = getattr(mod, f"render_{kind}")(mod.parse(text))
        else:
            kind = mermaid.detect_type(text)
            element = mermaid.render_element(text)
    except ValueError as exc:
        print(f"{_PROG}: {exc}", file=sys.stderr)
        return 1
    svg = str(element)

    if args.stats:
        import re

        print(f"{kind} diagram", file=sys.stderr)
        for label, pattern in (
            ("nodes", r"flow-node-group|timeline-node"),
            ("participants", r'class="actor actor-top"'),
            ("messages", r'class="messageText"'),
            ("edges", r'class="flow-edge'),
            ("slices", r'class="pieCircle"'),
        ):
            n = len(re.findall(pattern, svg))
            if n:
                print(f"  {n} {label}", file=sys.stderr)
        w = element.getAttribute("width")
        h = element.getAttribute("height")
        print(f"  {w} x {h} px", file=sys.stderr)

    if args.open:
        _open_in_browser(svg, wrap_html=True, title=f"{kind} diagram")
        return 0
    if args.html:
        svg = (
            "<!doctype html><meta charset=utf-8><title>mermaid</title>"
            "<style>body{margin:2rem;font-family:system-ui}</style>\n" + svg + "\n"
        )
    _write(svg, args.output)
    return 0


# --------------------------------------------------------------------------
# markdown  <->  html
# --------------------------------------------------------------------------


def _cmd_md(args) -> int:
    from .marked import marked

    html = marked(_read(args.input), {"gfm": args.gfm, "breaks": args.breaks, "pedantic": args.pedantic})
    _write(html, args.output)
    return 0


def _cmd_html2md(args) -> int:
    from .turndown import TurndownService

    service = TurndownService(
        heading_style=args.heading_style,
        bullet_list_marker=args.bullet,
        code_block_style=args.code_block_style,
    )
    if args.gfm:
        from .turndown.gfm import gfm

        service.use(gfm)
    _write(service.turndown(_read(args.input)), args.output)
    return 0


# --------------------------------------------------------------------------
# readability
# --------------------------------------------------------------------------


def _cmd_read(args) -> int:
    import domonic

    from .readability import Readability

    source = args.input
    if source and (source.startswith("http://") or source.startswith("https://")):
        import urllib.request

        req = urllib.request.Request(source, headers={"User-Agent": "dlx/readability"})
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - user-supplied URL
            raw = resp.read().decode("utf-8", "replace")
        base = source
    else:
        raw = _read(source)
        base = ""

    doc = domonic.domonic.parseString(raw)
    article = Readability(doc, char_threshold=120).parse()
    if not article:
        print(f"{_PROG}: no article content found", file=sys.stderr)
        return 1

    if args.json:
        payload = {k: v for k, v in article.items() if k != "content"}
        _write(json.dumps(payload, indent=2, default=str), args.output)
        return 0

    content = article["content"]
    if args.md:
        from .turndown import turndown

        title = article.get("title") or ""
        content = (f"# {title}\n\n" if title else "") + turndown(content)
    _write(content, args.output)
    return 0


# --------------------------------------------------------------------------
# dompurify
# --------------------------------------------------------------------------


def _cmd_sanitize(args) -> int:
    from .dompurify import DOMPurify

    profiles = {
        "html": {"USE_PROFILES": {"html": True}},
        "svg": {"USE_PROFILES": {"svg": True, "svgFilters": True}},
        "mathml": {"USE_PROFILES": {"mathMl": True}},
        "all": {},
    }
    cfg = dict(profiles.get(args.profile, {}))
    if args.allow_tags:
        cfg["ADD_TAGS"] = args.allow_tags.split(",")
    if args.allow_attr:
        cfg["ADD_ATTR"] = args.allow_attr.split(",")
    if args.strip_tags:
        cfg["FORBID_TAGS"] = args.strip_tags.split(",")

    purifier = DOMPurify()
    clean = purifier.sanitize(_read(args.input), cfg)
    _write(clean, args.output)
    if args.report and purifier.removed:
        print(f"{_PROG}: removed {len(purifier.removed)} item(s):", file=sys.stderr)
        for item in purifier.removed:
            print(f"  {json.dumps(item, default=str)}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------
# validator
# --------------------------------------------------------------------------


def _cmd_validate(args) -> int:
    from . import validator

    if args.list or not args.check:
        names = sorted(n for n in dir(validator) if n[:1].islower() and not n.startswith("_"))
        for n in names:
            print(n)
        return 0

    fn = getattr(validator, args.check, None)
    if not callable(fn):
        print(f"{_PROG}: unknown check {args.check!r} (try 'dlx validate --list')", file=sys.stderr)
        return 2

    call_args = []
    for a in args.args:
        try:
            call_args.append(json.loads(a))
        except (ValueError, TypeError):
            call_args.append(a)

    try:
        result = fn(*call_args)
    except Exception as exc:  # noqa: BLE001 - surface the library's error
        print(f"{_PROG}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if isinstance(result, bool):
        print("true" if result else "false")
        return 0 if result else 1
    print(result if isinstance(result, str) else json.dumps(result, default=str))
    return 0


# --------------------------------------------------------------------------
# qs
# --------------------------------------------------------------------------


def _cmd_qs(args) -> int:
    from . import qs

    if args.mode == "parse":
        data = qs.parse(args.value, {"depth": args.depth})
        _write(json.dumps(data, indent=2, default=str), args.output)
    else:
        try:
            obj = json.loads(args.value)
        except ValueError as exc:
            print(f"{_PROG}: stringify needs a JSON object: {exc}", file=sys.stderr)
            return 2
        _write(qs.stringify(obj), args.output)
    return 0


# --------------------------------------------------------------------------
# dagre  (edge-list DSL -> laid-out svg)
# --------------------------------------------------------------------------


def _cmd_dagre(args) -> int:
    import re

    from .dagre import Graph, layout

    text = _read(args.input)
    g = Graph({"multigraph": True, "compound": True})
    g.setGraph({"rankdir": args.rankdir.upper(), "nodesep": 40, "ranksep": 50, "marginx": 8, "marginy": 8})
    g.setDefaultEdgeLabel(lambda *a: {})

    edge_re = re.compile(r"^\s*(\S+)\s*(?:->|--|\s)\s*(\S+)\s*(?:#\s*(.+))?$")
    seen: set[str] = set()

    def node(v: str) -> None:
        if v not in seen:
            seen.add(v)
            w = 24 + 9 * len(v)
            g.setNode(v, {"width": w, "height": 32, "label": v})

    for line in text.splitlines():
        line = line.split("//", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        m = edge_re.match(line)
        if m:
            a, b, elabel = m.group(1), m.group(2), m.group(3)
            node(a)
            node(b)
            g.setEdge(a, b, {"label": elabel} if elabel else {})
        elif line and " " not in line:
            node(line)

    if not seen:
        print(f"{_PROG}: no nodes -- give lines like 'a -> b' or 'a b'", file=sys.stderr)
        return 1

    layout(g)
    gl = g.graph()
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {round(gl["width"])} {round(gl["height"])}" '
        f'width="{round(gl["width"])}" height="{round(gl["height"])}">',
        '<defs><marker id="a" refX="9" refY="5" markerWidth="10" markerHeight="10" orient="auto" '
        'markerUnits="userSpaceOnUse"><path d="M0 0L10 5L0 10z" fill="#333"/></marker></defs>',
        '<style>text{font:13px system-ui;fill:#222}rect{fill:#eef;stroke:#66a}'
        "path{fill:none;stroke:#333;stroke-width:1.5px}</style>",
    ]
    for e in g.edges():
        pts = g.edge(e).get("points") or []
        if len(pts) >= 2:
            d = "M " + " L ".join(f'{p["x"]:.1f},{p["y"]:.1f}' for p in pts)
            parts.append(f'<path d="{d}" marker-end="url(#a)"/>')
    for v in g.nodes():
        n = g.node(v)
        if n.get("x") is None:
            continue
        x = n["x"] - n["width"] / 2
        y = n["y"] - n["height"] / 2
        parts.append(f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{n["width"]:.1f}" height="{n["height"]:.1f}" rx="4"/>'
                     f'<text x="{n["x"]:.1f}" y="{n["y"]:.1f}" text-anchor="middle" '
                     f'dominant-baseline="central">{n["label"]}</text></g>')
    parts.append("</svg>")
    svg = "".join(parts)
    if args.open:
        _open_in_browser(svg, wrap_html=True, title="dagre graph")
        return 0
    _write(svg, args.output)
    return 0


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Command-line front end for the domonic-libs ports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="run 'dlx <command> -h' for command options",
    )
    parser.add_argument("-V", "--version", action="version", version=f"domonic-libs {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    m = sub.add_parser("mermaid", help="render diagram text to SVG (flowchart / sequence / pie / timeline)")
    _io_args(m, input_help="diagram file ('-' or omitted = stdin)")
    m.add_argument("--type", choices=["flowchart", "sequence", "pie", "timeline"], help="force a diagram type")
    m.add_argument("--html", action="store_true", help="wrap the SVG in a minimal HTML page")
    m.add_argument("--open", action="store_true", help="render and open in the default browser")
    m.add_argument("--stats", action="store_true", help="print counts to stderr")
    m.add_argument("--list", action="store_true", help="list supported diagram types and exit")
    m.set_defaults(func=_cmd_mermaid)

    md = sub.add_parser("md", help="Markdown to HTML (marked)")
    _io_args(md)
    md.add_argument("--no-gfm", dest="gfm", action="store_false", help="disable GitHub-flavoured Markdown")
    md.add_argument("--breaks", action="store_true", help="turn single newlines into <br>")
    md.add_argument("--pedantic", action="store_true", help="original Markdown.pl quirks")
    md.set_defaults(func=_cmd_md, gfm=True)

    h2 = sub.add_parser("html2md", help="HTML to Markdown (turndown)")
    _io_args(h2)
    h2.add_argument("--gfm", action="store_true", help="enable the GFM plugin (tables, strikethrough, task lists)")
    h2.add_argument("--heading-style", choices=["setext", "atx"], default="atx")
    h2.add_argument("--code-block-style", choices=["indented", "fenced"], default="fenced")
    h2.add_argument("--bullet", choices=["-", "*", "+"], default="-", help="bullet list marker")
    h2.set_defaults(func=_cmd_html2md)

    rd = sub.add_parser("read", help="extract the main article from a URL or HTML file (readability)")
    rd.add_argument("input", help="URL, or HTML file ('-' = stdin)")
    rd.add_argument("-o", "--output", metavar="FILE")
    rd.add_argument("--md", action="store_true", help="convert the extracted article to Markdown")
    rd.add_argument("--json", action="store_true", help="print the article metadata as JSON")
    rd.set_defaults(func=_cmd_read)

    sn = sub.add_parser("sanitize", help="sanitise hostile HTML (DOMPurify)")
    _io_args(sn)
    sn.add_argument("--profile", choices=["html", "svg", "mathml", "all"], default="all")
    sn.add_argument("--allow-tags", metavar="A,B", help="extra tags to allow")
    sn.add_argument("--allow-attr", metavar="A,B", help="extra attributes to allow")
    sn.add_argument("--strip-tags", metavar="A,B", help="tags to forbid")
    sn.add_argument("--report", action="store_true", help="list removed nodes/attributes on stderr")
    sn.set_defaults(func=_cmd_sanitize)

    vl = sub.add_parser("validate", help="run a validator.js check: dlx validate isEmail ada@example.com")
    vl.add_argument("check", nargs="?", help="check name, e.g. isEmail, isURL, isIBAN")
    vl.add_argument("args", nargs="*", help="value then any options (JSON literals are parsed)")
    vl.add_argument("--list", action="store_true", help="list every available check")
    vl.set_defaults(func=_cmd_validate)

    qsp = sub.add_parser("qs", help="parse or build a query string")
    qsp.add_argument("mode", choices=["parse", "stringify"])
    qsp.add_argument("value", help="a query string (parse) or a JSON object (stringify)")
    qsp.add_argument("-o", "--output", metavar="FILE")
    qsp.add_argument("--depth", type=int, default=5, help="max nesting depth for parse")
    qsp.set_defaults(func=_cmd_qs)

    dg = sub.add_parser("dagre", help="lay out a graph (lines of 'a -> b') and draw it as SVG")
    _io_args(dg, input_help="edge-list file: one 'a -> b' or 'a b' per line ('#label' for edge text)")
    dg.add_argument("--rankdir", choices=["tb", "bt", "lr", "rl", "TB", "BT", "LR", "RL"], default="tb")
    dg.add_argument("--open", action="store_true", help="draw and open in the browser")
    dg.set_defaults(func=_cmd_dagre)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except FileNotFoundError as exc:
        print(f"{_PROG}: {exc.strerror}: {exc.filename}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

from domonic import domonic

from htmlparser2 import install_domonic_parser


DEFAULT_PARSERS = [
    "htmlparser2",
    "html.parser",
    "html5lib",
    "lxml_html",
    "selectolax",
    "turbohtml",
    "markupever",
    "html5_parser",
    "justhtml",
    "expat",
]


def default_fixture() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "benchmarks" / "html_meaty_page.html",
        here.parents[2] / "projects" / "domonic" / "benchmarks" / "html_meaty_page.html",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def benchmark_parser(html: str, parser_name: str, iterations: int) -> dict[str, object]:
    timings = []
    title_text = ""
    error = None
    skipped = None

    for _ in range(iterations):
        start = time.perf_counter()
        try:
            page = domonic.parseString(html, parser=parser_name)
            timings.append(time.perf_counter() - start)
            if not title_text and page is not None:
                title = page.querySelector("title") if hasattr(page, "querySelector") else None
                title_text = title.text if title is not None else ""
        except ModuleNotFoundError as exc:
            skipped = f"missing optional dependency: {exc.name}"
            break
        except ImportError as exc:
            skipped = f"missing optional dependency: {exc}"
            break
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            break

    if skipped is not None:
        return {"parser": parser_name, "ok": False, "skipped": True, "error": skipped}
    if error is not None:
        return {"parser": parser_name, "ok": False, "skipped": False, "error": error}
    return {
        "parser": parser_name,
        "ok": True,
        "skipped": False,
        "iterations": iterations,
        "mean_ms": statistics.mean(timings) * 1000,
        "median_ms": statistics.median(timings) * 1000,
        "min_ms": min(timings) * 1000,
        "max_ms": max(timings) * 1000,
        "title": title_text.strip(),
    }


def print_results(results: list[dict[str, object]], page_path: Path, html: str) -> None:
    print(f"Benchmark page: {page_path}")
    print(f"HTML size: {len(html):,} bytes")
    print("")
    print(f"{'parser':<14} {'status':<8} {'mean ms':>10} {'median ms':>10} {'min ms':>10} {'max ms':>10}  title")
    print("-" * 96)
    for row in results:
        if not row["ok"]:
            status = "SKIP" if row.get("skipped") else "FAIL"
            print(f"{row['parser']:<14} {status:<8} {'-':>10} {'-':>10} {'-':>10} {'-':>10}  {row['error']}")
            continue
        print(
            f"{row['parser']:<14} {'OK':<8} "
            f"{row['mean_ms']:>10.2f} {row['median_ms']:>10.2f} {row['min_ms']:>10.2f} {row['max_ms']:>10.2f}  "
            f"{row['title']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark domonic parser backends with htmlparser2 installed.")
    parser.add_argument("page", nargs="?", default=str(default_fixture()))
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument("--parsers", nargs="*", default=DEFAULT_PARSERS)
    parser.add_argument("--prefer-auto", action="store_true", help="make parser='auto' try htmlparser2 first")
    args = parser.parse_args(argv)

    install_domonic_parser(prefer_auto=args.prefer_auto)
    page_path = Path(args.page)
    html = page_path.read_text(encoding="utf-8")
    results = [benchmark_parser(html, name, args.iterations) for name in args.parsers]
    print_results(results, page_path, html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

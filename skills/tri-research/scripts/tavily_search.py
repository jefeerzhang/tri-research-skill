#!/usr/bin/env python3
"""Tavily search wrapper for tri-research.

CLI interface for Tavily search API, callable via bash from the lead agent.
Declares a TavilyBackend spec over the shared CLI skeleton in
`_search_cli.py` (same pattern as exa_search.py).

Usage:
  python tavily_search.py search <query> [--max-results N] [--depth basic|advanced] [--time-range RANGE]
  python tavily_search.py batch_search --query "q1" --query "q2" [--max-results N] [--depth basic|advanced]
  python tavily_search.py extract <url> [--depth basic|advanced]
  python tavily_search.py check
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Make sibling `_search_cli` importable regardless of how this file is
# invoked (same bootstrap as state_machine.py / validate_report.py).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import _search_cli  # noqa: E402

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore[misc,assignment]


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": result.get("title", ""),
        "url": result.get("url", ""),
        "snippet": result.get("snippet", ""),
        "content": (result.get("content") or "")[:5000],
        "score": result.get("score"),
    }


def _make_client(api_key: str) -> Any:
    return TavilyClient(api_key=api_key)


class TavilyBackend(_search_cli.Backend):
    name = "Tavily"
    help = "Tavily search CLI for tri-research"
    sdk = TavilyClient
    missing_sdk_message = "tavily-python not installed"
    env_key = "TAVILY_API_KEY"
    # staticmethod: a plain lambda in the class body would be descriptor-bound
    # to the instance, so client_factory(api_key) would receive 2 arguments.
    client_factory = staticmethod(_make_client)
    flags = [
        _search_cli.Flag("max_results", ("--max-results",), "Number of results (default: 5)", type=int, default=5),
        _search_cli.Flag("depth", ("--depth",), "Search depth", choices=["basic", "advanced"], default="basic"),
        _search_cli.Flag("time_range", ("--time-range",), "Time range filter", choices=["day", "week", "month", "year"]),
        _search_cli.Flag("include_domains", ("--include-domains",), "Comma-separated domains to include"),
        _search_cli.Flag("exclude_domains", ("--exclude-domains",), "Comma-separated domains to exclude"),
    ]

    def probe(self, client: Any) -> bool:
        client.search(query="test", max_results=1, search_depth="basic")
        return True

    def search(self, client: Any, query: str, options: dict[str, Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"query": query, **options}
        if options.get("include_domains"):
            kwargs["include_domains"] = options["include_domains"].split(",")
        if options.get("exclude_domains"):
            kwargs["exclude_domains"] = options["exclude_domains"].split(",")
        resp = client.search(**kwargs)
        return {
            "max_results": options.get("max_results", 5),
            "search_depth": options.get("depth", "basic"),
            "results": [_normalize_result(r) for r in resp.get("results", [])],
        }


backend = TavilyBackend()


def _cmd_extract(args: Any) -> None:
    client = backend.client()
    try:
        resp = client.extract(urls=[args.url], extract_depth=args.depth)
    except Exception as exc:
        print(json.dumps({"error": str(exc), "url": args.url}))
        sys.exit(1)
    pages = []
    for p in resp.get("results", []):
        pages.append({
            "url": p.get("url", args.url),
            "title": p.get("title", ""),
            "content": (p.get("content") or "")[:20000],
        })
    if pages:
        print(json.dumps(pages[0], ensure_ascii=False))
    else:
        print(json.dumps({"error": "no content extracted", "url": args.url}))
        sys.exit(1)


def _add_extract_args(parser: Any) -> None:
    parser.add_argument("url", help="URL to extract")
    parser.add_argument("--depth", choices=["basic", "advanced"], default="advanced", help="Extract depth")


backend.commands = [
    _search_cli.Command("extract", "Extract content from a URL", _add_extract_args, _cmd_extract),
]


def cmd_check() -> None:
    """Availability probe (no-arg entry kept for the regression tests)."""
    _search_cli.check(backend)


def main(argv: list[str] | None = None) -> int:
    return _search_cli.run(backend, argv)


if __name__ == "__main__":
    raise SystemExit(main())

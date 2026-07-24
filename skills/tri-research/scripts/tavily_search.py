"""Tavily search wrapper for tri-research.

CLI interface for Tavily search API, callable via bash from the lead agent.
Reuses the existing exa_search.py / anysearch_cli.py pattern.

Usage:
  python tavily_search.py search <query> [--max-results N] [--depth basic|advanced] [--time-range RANGE]
  python tavily_search.py batch_search --query "q1" --query "q2" [--max-results N] [--depth basic|advanced]
  python tavily_search.py extract <url> [--depth basic|advanced]
  python tavily_search.py check
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore[misc,assignment]


def _client() -> "TavilyClient":
    if TavilyClient is None:
        print(json.dumps({"available": False, "error": "tavily-python not installed"}))
        sys.exit(1)
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        print(json.dumps({"available": False, "error": "TAVILY_API_KEY not set"}))
        sys.exit(1)
    return TavilyClient(api_key=api_key)


def cmd_check() -> None:
    if TavilyClient is None:
        print(json.dumps({"available": False, "error": "tavily-python not installed"}))
        return
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        print(json.dumps({"available": False, "error": "TAVILY_API_KEY not set"}))
        return
    try:
        c = _client()
        c.search(query="test", max_results=1, search_depth="basic")
        print(json.dumps({"available": True}))
    except Exception as e:
        print(json.dumps({"available": False, "error": str(e)}))


def _normalize_result(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": r.get("title", ""),
        "url": r.get("url", ""),
        "snippet": r.get("snippet", ""),
        "content": (r.get("content") or "")[:5000],
        "score": r.get("score"),
    }


def cmd_search(args: argparse.Namespace) -> None:
    c = _client()
    kwargs: dict[str, Any] = {
        "query": args.query,
        "max_results": args.max_results,
        "search_depth": args.depth,
    }
    if args.time_range:
        kwargs["time_range"] = args.time_range
    if args.include_domains:
        kwargs["include_domains"] = args.include_domains.split(",")
    if args.exclude_domains:
        kwargs["exclude_domains"] = args.exclude_domains.split(",")
    try:
        resp = c.search(**kwargs)
        results = [_normalize_result(r) for r in resp.get("results", [])]
        print(json.dumps({
            "query": args.query,
            "max_results": args.max_results,
            "search_depth": args.depth,
            "results": results,
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "query": args.query}))
        sys.exit(1)


def cmd_batch_search(args: argparse.Namespace) -> None:
    c = _client()
    all_results: dict[str, Any] = {}
    for q in args.query:
        kwargs: dict[str, Any] = {
            "query": q,
            "max_results": args.max_results,
            "search_depth": args.depth,
        }
        if args.time_range:
            kwargs["time_range"] = args.time_range
        try:
            resp = c.search(**kwargs)
            all_results[q] = [_normalize_result(r) for r in resp.get("results", [])]
        except Exception as e:
            all_results[q] = {"error": str(e)}
    print(json.dumps(all_results, ensure_ascii=False))


def cmd_extract(args: argparse.Namespace) -> None:
    c = _client()
    kwargs: dict[str, Any] = {
        "urls": [args.url],
        "extract_depth": args.depth,
    }
    try:
        resp = c.extract(**kwargs)
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
    except Exception as e:
        print(json.dumps({"error": str(e), "url": args.url}))
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Tavily search CLI for tri-research")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Check Tavily availability")

    search_p = sub.add_parser("search", help="Search the web via Tavily")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("--max-results", type=int, default=5, help="Number of results (default: 5)")
    search_p.add_argument("--depth", choices=["basic", "advanced"], default="basic", help="Search depth")
    search_p.add_argument("--time-range", choices=["day", "week", "month", "year"], help="Time range filter")
    search_p.add_argument("--include-domains", help="Comma-separated domains to include")
    search_p.add_argument("--exclude-domains", help="Comma-separated domains to exclude")

    batch_p = sub.add_parser("batch_search", help="Batch search multiple queries")
    batch_p.add_argument("--query", action="append", required=True, help="Query (can repeat)")
    batch_p.add_argument("--max-results", type=int, default=5, help="Number of results per query")
    batch_p.add_argument("--depth", choices=["basic", "advanced"], default="basic", help="Search depth")
    batch_p.add_argument("--time-range", choices=["day", "week", "month", "year"], help="Time range filter")

    extract_p = sub.add_parser("extract", help="Extract content from a URL")
    extract_p.add_argument("url", help="URL to extract")
    extract_p.add_argument("--depth", choices=["basic", "advanced"], default="advanced", help="Extract depth")

    return p


def main() -> None:
    p = build_parser()
    a = p.parse_args()
    if a.command == "check":
        cmd_check()
    elif a.command == "search":
        cmd_search(a)
    elif a.command == "batch_search":
        cmd_batch_search(a)
    elif a.command == "extract":
        cmd_extract(a)


if __name__ == "__main__":
    main()

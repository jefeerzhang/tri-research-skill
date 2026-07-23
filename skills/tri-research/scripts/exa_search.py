"""Exa search wrapper for tri-research.

CLI interface for Exa AI search API, callable via bash from sub-agents.
Reuses the existing AnySearch/SciVerse pattern.

Usage:
  python exa_search.py search <query> [--category CAT] [--num-results N] [--type TYPE]
  python exa_search.py batch_search --query "q1" --query "q2" [--category CAT] [--num-results N]
  python exa_search.py answer <query>
  python exa_search.py contents <url>
  python exa_search.py check
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import exa_py
except ImportError:
    exa_py = None


def _client() -> "exa_py.Exa":
    if exa_py is None:
        print(json.dumps({"error": "exa-py not installed", "available": False}))
        sys.exit(1)
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        print(json.dumps({"error": "EXA_API_KEY not set", "available": False}))
        sys.exit(1)
    return exa_py.Exa(api_key=api_key)


def cmd_check() -> None:
    if exa_py is None:
        print(json.dumps({"available": False, "error": "exa-py not installed"}))
        return
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        print(json.dumps({"available": False, "error": "EXA_API_KEY not set"}))
        return
    try:
        c = _client()
        c.search("test", num_results=1)
        print(json.dumps({"available": True}))
    except Exception as e:
        print(json.dumps({"available": False, "error": str(e)}))


def cmd_search(args: argparse.Namespace) -> None:
    c = _client()
    kwargs = {"num_results": args.num_results}
    if args.category:
        kwargs["category"] = args.category
    if args.type:
        kwargs["type"] = args.type
    try:
        resp = c.search(args.query, **kwargs)
        results = []
        for r in resp.results:
            results.append({
                "title": r.title,
                "url": r.url,
                "snippet": (r.text or "")[:500] if hasattr(r, "text") and r.text else "",
                "published_date": str(r.published_date) if hasattr(r, "published_date") and r.published_date else "",
            })
        print(json.dumps({
            "query": args.query,
            "category": args.category or "general",
            "num_results": len(results),
            "results": results,
            "autoprompt_string": getattr(resp, "autoprompt_string", None),
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "query": args.query}))


def cmd_batch_search(args: argparse.Namespace) -> None:
    c = _client()
    all_results = {}
    for q in args.query:
        try:
            kwargs = {"num_results": args.num_results}
            if args.category:
                kwargs["category"] = args.category
            resp = c.search(q, **kwargs)
            results = []
            for r in resp.results:
                results.append({
                    "title": r.title,
                    "url": r.url,
                    "snippet": (r.text or "")[:500] if hasattr(r, "text") and r.text else "",
                    "published_date": str(r.published_date) if hasattr(r, "published_date") and r.published_date else "",
                })
            all_results[q] = results
        except Exception as e:
            all_results[q] = {"error": str(e)}
    print(json.dumps(all_results, ensure_ascii=False))


def cmd_answer(args: argparse.Namespace) -> None:
    c = _client()
    try:
        resp = c.answer(args.query, text=True)
        citations = []
        if hasattr(resp, "citations") and resp.citations:
            for cit in resp.citations:
                citations.append({
                    "title": cit.title if hasattr(cit, "title") else "",
                    "url": cit.url if hasattr(cit, "url") else "",
                    "text": (cit.text or "")[:1000] if hasattr(cit, "text") and cit.text else "",
                })
        print(json.dumps({
            "query": args.query,
            "answer": resp.answer if hasattr(resp, "answer") else "",
            "citations": citations,
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "query": args.query}))


def cmd_contents(args: argparse.Namespace) -> None:
    c = _client()
    try:
        resp = c.get_contents(urls=[args.url])
        pages = []
        for p in resp.results:
            pages.append({
                "url": p.url,
                "title": p.title if hasattr(p, "title") else "",
                "text": (p.text or "")[:5000] if hasattr(p, "text") and p.text else "",
            })
        print(json.dumps(pages, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "url": args.url}))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Exa search CLI for tri-research")
    sub = p.add_subparsers(dest="command", required=True)

    check_p = sub.add_parser("check", help="Check Exa availability")

    search_p = sub.add_parser("search", help="Search the web via Exa")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("--category", help="Search category: company, research paper, news, pdf, etc.")
    search_p.add_argument("--num-results", type=int, default=5, help="Number of results (default: 5)")
    search_p.add_argument("--type", help="Search type: auto, fast, neural, deep, deep-lite")

    batch_p = sub.add_parser("batch_search", help="Batch search multiple queries")
    batch_p.add_argument("--query", action="append", required=True, help="Query (can repeat)")
    batch_p.add_argument("--category", help="Search category")
    batch_p.add_argument("--num-results", type=int, default=5, help="Number of results per query")

    ans_p = sub.add_parser("answer", help="Ask Exa a question with grounded answer")
    ans_p.add_argument("query", help="Question to answer")

    cont_p = sub.add_parser("contents", help="Extract content from a URL")
    cont_p.add_argument("url", help="URL to extract")

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
    elif a.command == "answer":
        cmd_answer(a)
    elif a.command == "contents":
        cmd_contents(a)


if __name__ == "__main__":
    main()

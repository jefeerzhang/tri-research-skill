#!/usr/bin/env python3
"""Exa search wrapper for tri-research.

CLI interface for Exa AI search API, callable via bash from sub-agents.
Declares an ExaBackend spec over the shared CLI skeleton in `_search_cli.py`.

Usage:
  python exa_search.py search <query> [--category CAT] [--num-results N] [--type TYPE]
  python exa_search.py batch_search --query "q1" --query "q2" [--category CAT] [--num-results N]
  python exa_search.py answer <query>
  python exa_search.py contents <url>
  python exa_search.py check
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
    import exa_py
except ImportError:
    exa_py = None  # type: ignore[assignment]


def _normalize_result(result: Any) -> dict[str, Any]:
    return {
        "title": result.title,
        "url": result.url,
        "snippet": (result.text or "")[:500] if hasattr(result, "text") and result.text else "",
        "published_date": str(result.published_date) if hasattr(result, "published_date") and result.published_date else "",
    }


def _make_client(api_key: str) -> Any:
    return exa_py.Exa(api_key=api_key)


class ExaBackend(_search_cli.Backend):
    name = "Exa"
    help = "Exa search CLI for tri-research"
    sdk = exa_py
    missing_sdk_message = "exa-py not installed"
    env_key = "EXA_API_KEY"
    # staticmethod: a plain lambda in the class body would be descriptor-bound
    # to the instance, so client_factory(api_key) would receive 2 arguments.
    client_factory = staticmethod(_make_client)
    flags = [
        _search_cli.Flag("category", ("--category",), "Search category: company, research paper, news, pdf, etc."),
        _search_cli.Flag("num_results", ("--num-results",), "Number of results (default: 5)", type=int, default=5),
        _search_cli.Flag("type", ("--type",), "Search type: auto, fast, neural, deep, deep-lite"),
    ]

    def probe(self, client: Any) -> bool:
        client.search("test", num_results=1)
        return True

    def search(self, client: Any, query: str, options: dict[str, Any]) -> dict[str, Any]:
        resp = client.search(query, **options)
        return {
            "category": options.get("category") or "general",
            "num_results": len(resp.results),
            "results": [_normalize_result(r) for r in resp.results],
            "autoprompt_string": getattr(resp, "autoprompt_string", None),
        }


backend = ExaBackend()


def _cmd_answer(args: Any) -> None:
    client = backend.client()
    try:
        resp = client.answer(args.query, text=True)
    except Exception as exc:
        print(json.dumps({"error": str(exc), "query": args.query}))
        sys.exit(1)
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


def _cmd_contents(args: Any) -> None:
    client = backend.client()
    try:
        resp = client.get_contents(urls=[args.url])
    except Exception as exc:
        print(json.dumps({"error": str(exc), "url": args.url}))
        sys.exit(1)
    pages = []
    for p in resp.results:
        pages.append({
            "url": p.url,
            "title": p.title if hasattr(p, "title") else "",
            "text": (p.text or "")[:5000] if hasattr(p, "text") and p.text else "",
        })
    print(json.dumps(pages, ensure_ascii=False))


backend.commands = [
    _search_cli.Command(
        "answer",
        "Ask Exa a question with grounded answer",
        lambda p: p.add_argument("query", help="Question to answer"),
        _cmd_answer,
    ),
    _search_cli.Command(
        "contents",
        "Extract content from a URL",
        lambda p: p.add_argument("url", help="URL to extract"),
        _cmd_contents,
    ),
]


def cmd_check() -> None:
    """Availability probe (no-arg entry kept for the regression tests)."""
    _search_cli.check(backend)


def main(argv: list[str] | None = None) -> int:
    return _search_cli.run(backend, argv)


if __name__ == "__main__":
    raise SystemExit(main())

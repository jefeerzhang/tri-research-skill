"""Shared search-backend module for tri-research (Exa + Tavily).

Exa and Tavily backends are declared here over the shared CLI skeleton in
`_search_cli.py`. SerpApi lives in `skills/serpapi/scripts/serpapi_cli.py`
because its CLI surface (key loading, proxy handling, three extra commands)
is substantially wider than Exa / Tavily — co-locating the full SerpApi
implementation in its own wrapper keeps this module symmetric (Exa + Tavily,
both thin) instead of burying SerpApi-specific glue here.

The per-backend CLI scripts (`exa_search.py`, `tavily_search.py`) remain
thin entry points so existing callers, sub-agents and tests keep working
unchanged.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Make sibling `_search_cli` importable regardless of how this file is
# invoked (same bootstrap as state_machine.py / validate_report.py).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import _search_cli  # noqa: E402
from _search_registry import REGISTRY, BackendSpec  # noqa: E402

try:
    import exa_py
except ImportError:
    exa_py = None  # type: ignore[assignment]

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Exa
# ---------------------------------------------------------------------------


def _exa_normalize_result(result: Any) -> dict[str, Any]:
    return {
        "title": result.title,
        "url": result.url,
        "snippet": (result.text or "")[:500] if hasattr(result, "text") and result.text else "",
        "published_date": str(result.published_date)
        if hasattr(result, "published_date") and result.published_date
        else "",
    }


def _exa_make_client(api_key: str) -> Any:
    return exa_py.Exa(api_key=api_key)


class ExaBackend(_search_cli.Backend):
    name = "Exa"
    help = "Exa search CLI for tri-research"
    sdk = exa_py
    missing_sdk_message = "exa-py not installed"
    env_key = "EXA_API_KEY"
    # staticmethod: a plain lambda in the class body would be descriptor-bound
    # to the instance, so client_factory(api_key) would receive 2 arguments.
    client_factory = staticmethod(_exa_make_client)
    flags = [
        _search_cli.Flag("category", ("--category",), "Search category: company, research paper, news, pdf, etc."),
        _search_cli.Flag("num_results", ("--num-results",), "Number of results (default: 5)", type=int, default=5),
        _search_cli.Flag("type", ("--type",), "Search type: auto, fast, neural, deep, deep-lite"),
    ]

    def probe(self, client: Any) -> bool:
        # contents=False: probe must be fast and must not hang fetching a page.
        client.search("test", num_results=1, contents=False)
        return True

    def search(self, client: Any, query: str, options: dict[str, Any]) -> dict[str, Any]:
        resp = client.search(query, **options)
        return {
            "category": options.get("category") or "general",
            "num_results": len(resp.results),
            "results": [_exa_normalize_result(r) for r in resp.results],
            "autoprompt_string": getattr(resp, "autoprompt_string", None),
        }


def _exa_cmd_answer(args: Any) -> None:
    # Contract: extra commands share retry/timeout/circuit via invoke and respect --no-proxy
    if getattr(args, "no_proxy", False):
        for _p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(_p, None)
    # Use KeyProvider for .env support (unified with Registry)
    try:
        from _search_registry import KeyProvider  # noqa: E402

        api_key = KeyProvider.resolve(None, EXA_BACKEND.env_key)
    except ImportError:
        api_key = os.environ.get(EXA_BACKEND.env_key)
    if not api_key:
        print(json.dumps({"error": f"{EXA_BACKEND.env_key} not set", "query": args.query}))
        sys.exit(1)
    if EXA_BACKEND.sdk is None:
        print(json.dumps({"error": EXA_BACKEND.missing_sdk_message, "query": args.query}))
        sys.exit(1)
    client = EXA_BACKEND.client_factory(api_key)
    try:
        resp = _search_cli.invoke(EXA_BACKEND, lambda: client.answer(args.query, text=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "query": args.query}))
        sys.exit(1)
    citations = []
    if hasattr(resp, "citations") and resp.citations:
        for cit in resp.citations:
            citations.append(
                {
                    "title": cit.title if hasattr(cit, "title") else "",
                    "url": cit.url if hasattr(cit, "url") else "",
                    "text": (cit.text or "")[:1000] if hasattr(cit, "text") and cit.text else "",
                }
            )
    print(
        json.dumps(
            {
                "query": args.query,
                "answer": resp.answer if hasattr(resp, "answer") else "",
                "citations": citations,
            },
            ensure_ascii=False,
        )
    )


def _exa_cmd_contents(args: Any) -> None:
    if getattr(args, "no_proxy", False):
        for _p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(_p, None)
    try:
        from _search_registry import KeyProvider  # noqa: E402

        api_key = KeyProvider.resolve(None, EXA_BACKEND.env_key)
    except ImportError:
        api_key = os.environ.get(EXA_BACKEND.env_key)
    if not api_key:
        print(json.dumps({"error": f"{EXA_BACKEND.env_key} not set", "url": args.url}))
        sys.exit(1)
    if EXA_BACKEND.sdk is None:
        print(json.dumps({"error": EXA_BACKEND.missing_sdk_message, "url": args.url}))
        sys.exit(1)
    client = EXA_BACKEND.client_factory(api_key)
    try:
        resp = _search_cli.invoke(EXA_BACKEND, lambda: client.get_contents(urls=[args.url]))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "url": args.url}))
        sys.exit(1)
    pages = []
    for p in resp.results:
        pages.append(
            {
                "url": p.url,
                "title": p.title if hasattr(p, "title") else "",
                "text": (p.text or "")[:5000] if hasattr(p, "text") and p.text else "",
            }
        )
    print(json.dumps(pages, ensure_ascii=False))


EXA_BACKEND = ExaBackend()
EXA_BACKEND.commands = [
    _search_cli.Command(
        "answer",
        "Ask Exa a question with grounded answer",
        lambda p: p.add_argument("query", help="Question to answer"),
        _exa_cmd_answer,
    ),
    _search_cli.Command(
        "contents",
        "Extract content from a URL",
        lambda p: p.add_argument("url", help="URL to extract"),
        _exa_cmd_contents,
    ),
]

# Register with global Registry (expand step #7 keeps old path working; new
# callers can use REGISTRY.search("exa", ...) for uniform SearchResult).
try:
    REGISTRY.register(BackendSpec(name="exa", backend=EXA_BACKEND, env_key="EXA_API_KEY"))
except ValueError:
    pass  # already registered (re-import in tests with sys.modules["tavily"] blocked)


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------


def _tavily_normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": result.get("title", ""),
        "url": result.get("url", ""),
        "snippet": result.get("snippet", ""),
        "content": (result.get("content") or "")[:5000],
        "score": result.get("score"),
    }


def _tavily_make_client(api_key: str) -> Any:
    return TavilyClient(api_key=api_key)


class TavilyBackend(_search_cli.Backend):
    name = "Tavily"
    help = "Tavily search CLI for tri-research"
    sdk = TavilyClient
    missing_sdk_message = "tavily-python not installed"
    env_key = "TAVILY_API_KEY"
    # staticmethod: a plain lambda in the class body would be descriptor-bound
    # to the instance, so client_factory(api_key) would receive 2 arguments.
    client_factory = staticmethod(_tavily_make_client)
    flags = [
        _search_cli.Flag("max_results", ("--max-results",), "Number of results (default: 5)", type=int, default=5),
        _search_cli.Flag("depth", ("--depth",), "Search depth", choices=["basic", "advanced"], default="basic"),
        _search_cli.Flag(
            "time_range", ("--time-range",), "Time range filter", choices=["day", "week", "month", "year"]
        ),
        _search_cli.Flag("include_domains", ("--include-domains",), "Comma-separated domains to include"),
        _search_cli.Flag("exclude_domains", ("--exclude-domains",), "Comma-separated domains to exclude"),
    ]

    def probe(self, client: Any) -> bool:
        client.search(query="test", max_results=1, search_depth="basic")
        return True

    def search(self, client: Any, query: str, options: dict[str, Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"query": query, **options}
        # The CLI flag dest is "depth", but the Tavily API parameter is
        # "search_depth". Forwarding the raw dest silently dropped --depth:
        # the SDK accepts unknown **kwargs without forwarding them to the
        # API, so `--depth advanced` never took effect while the output
        # metadata still claimed search_depth=advanced.
        if "depth" in kwargs:
            kwargs["search_depth"] = kwargs.pop("depth")
        if options.get("include_domains"):
            kwargs["include_domains"] = options["include_domains"].split(",")
        if options.get("exclude_domains"):
            kwargs["exclude_domains"] = options["exclude_domains"].split(",")
        resp = client.search(**kwargs)
        return {
            "max_results": options.get("max_results", 5),
            "search_depth": options.get("depth", "basic"),
            "results": [_tavily_normalize_result(r) for r in resp.get("results", [])],
        }


def _tavily_cmd_extract(args: Any) -> None:
    if getattr(args, "no_proxy", False):
        for _p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(_p, None)
    try:
        from _search_registry import KeyProvider  # noqa: E402

        api_key = KeyProvider.resolve(None, TAVILY_BACKEND.env_key)
    except ImportError:
        api_key = os.environ.get(TAVILY_BACKEND.env_key)
    if not api_key:
        print(json.dumps({"error": f"{TAVILY_BACKEND.env_key} not set", "url": args.url}))
        sys.exit(1)
    if TAVILY_BACKEND.sdk is None:
        print(json.dumps({"error": TAVILY_BACKEND.missing_sdk_message, "url": args.url}))
        sys.exit(1)
    client = TAVILY_BACKEND.client_factory(api_key)
    try:
        resp = _search_cli.invoke(TAVILY_BACKEND, lambda: client.extract(urls=[args.url], extract_depth=args.depth))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "url": args.url}))
        sys.exit(1)
    pages = []
    for p in resp.get("results", []):
        pages.append(
            {
                "url": p.get("url", args.url),
                "title": p.get("title", ""),
                "content": (p.get("content") or "")[:20000],
            }
        )
    if pages:
        print(json.dumps(pages[0], ensure_ascii=False))
    else:
        print(json.dumps({"error": "no content extracted", "url": args.url}))
        sys.exit(1)


def _tavily_add_extract_args(parser: Any) -> None:
    parser.add_argument("url", help="URL to extract")
    parser.add_argument("--depth", choices=["basic", "advanced"], default="advanced", help="Extract depth")


TAVILY_BACKEND = TavilyBackend()
TAVILY_BACKEND.commands = [
    _search_cli.Command("extract", "Extract content from a URL", _tavily_add_extract_args, _tavily_cmd_extract),
]

try:
    REGISTRY.register(BackendSpec(name="tavily", backend=TAVILY_BACKEND, env_key="TAVILY_API_KEY"))
except ValueError:
    pass

# Expose global --no-proxy to Exa/Tavily via Registry (expand keeps old JSON shape)
EXA_BACKEND.global_flags = REGISTRY.global_flags  # type: ignore[assignment]
TAVILY_BACKEND.global_flags = REGISTRY.global_flags  # type: ignore[assignment]

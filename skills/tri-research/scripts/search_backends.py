"""Shared search-backend module for tri-research (Exa + Tavily + OpenAlex).

Exa, Tavily and OpenAlex backends are declared here over the shared CLI skeleton in
`_search_cli.py`. SerpApi lives in `skills/serpapi/scripts/serpapi_cli.py`
because its CLI surface (key loading, proxy handling, three extra commands)
is substantially wider than Exa / Tavily — co-locating the full SerpApi
implementation in its own wrapper keeps this module symmetric (Exa + Tavily,
both thin) instead of burying SerpApi-specific glue here.

The per-backend CLI scripts (`exa_search.py`, `tavily_search.py`) remain
thin entry points so existing callers, sub-agents and tests keep working
unchanged.

The extra commands here (`answer` / `contents` / `extract`) are declared
**managed**: `_search_cli.run_managed_command` performs proxy clearing,
key resolution (env + `.env`), the SDK-missing check, client build,
retry/timeout/circuit and all JSON printing — bodies below only shape one
SDK call into its output (see ADR-0002 for why SerpApi stays unmanaged).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Make sibling `_search_cli` importable regardless of how this file is
# invoked (same bootstrap as state_machine.py / validate_report.py).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import _search_cli  # noqa: E402
from _search_registry import REGISTRY, BackendSpec  # noqa: E402

# `sdk is None` is the module's existing "not installed" signal (ADR-0011 turns
# it into a readiness gap). The catch includes AttributeError on purpose: a
# shadowed or half-broken dependency raises that at import time, and this module
# is now loaded lazily by the Required gate — `state_machine start` must degrade
# to a reported gap, never to a traceback.
try:
    import exa_py
except (ImportError, AttributeError):
    exa_py = None  # type: ignore[assignment]

try:
    from tavily import TavilyClient
except (ImportError, AttributeError):
    TavilyClient = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Exa
# ---------------------------------------------------------------------------


def _exa_normalize_result(result: Any) -> dict[str, Any]:
    text = getattr(result, "text", None) or ""
    published = getattr(result, "published_date", None)
    return {
        "title": result.title,
        "url": result.url,
        "snippet": _search_cli.truncate(text, _search_cli.SNIPPET_LIMIT),
        "published_date": str(published) if published else "",
    }


def _exa_make_client(api_key: str) -> Any:
    return exa_py.Exa(api_key=api_key)


class ExaBackend(_search_cli.Backend):
    name = "Exa"
    help = "Exa search CLI for tri-research"
    sdk = exa_py
    missing_sdk_message = "exa-py not installed"
    env_key = "EXA_API_KEY"
    requirement = _search_cli.BackendRequirementLevel.REQUIRED
    env_file = _SCRIPT_DIR.parent / ".env"  # this skill's own .env (ADR-0004)
    requirement = _search_cli.BackendRequirementLevel.REQUIRED
    apply_url = "https://dashboard.exa.ai/api-keys"
    verify_cmd = "python scripts/exa_search.py check"
    configure_hint = f"pip install exa-py && export {env_key}=<key> ({apply_url})"
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


def _exa_answer(client: Any, args: Any) -> dict[str, Any]:
    """Managed body: one SDK call + citation shaping; lifecycle is skeleton's."""
    resp = client.answer(args.query, text=True)
    citations = [
        {
            "title": getattr(cit, "title", ""),
            "url": getattr(cit, "url", ""),
            "text": _search_cli.truncate(getattr(cit, "text", None), _search_cli.CITATION_TEXT_LIMIT),
        }
        for cit in getattr(resp, "citations", None) or []
    ]
    return {
        "query": args.query,
        "answer": getattr(resp, "answer", ""),
        "citations": citations,
    }


def _exa_contents(client: Any, args: Any) -> list[dict[str, Any]]:
    resp = client.get_contents(urls=[args.url])
    return [
        {
            "url": p.url,
            "title": getattr(p, "title", ""),
            "text": _search_cli.truncate(getattr(p, "text", None), _search_cli.CONTENT_LIMIT),
        }
        for p in resp.results
    ]


EXA_BACKEND = ExaBackend()
EXA_BACKEND.commands = [
    _search_cli.Command(
        "answer",
        "Ask Exa a question with grounded answer",
        lambda p: p.add_argument("query", help="Question to answer"),
        _exa_answer,
        managed=True,
        echo=lambda a: {"query": a.query},
    ),
    _search_cli.Command(
        "contents",
        "Extract content from a URL",
        lambda p: p.add_argument("url", help="URL to extract"),
        _exa_contents,
        managed=True,
        echo=lambda a: {"url": a.url},
    ),
]

# Register with global Registry (expand step #7 keeps old path working; new
# callers can use REGISTRY.search("exa", ...) for uniform SearchResult).
try:
    REGISTRY.register(BackendSpec(name="exa", backend=EXA_BACKEND))
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
        "content": _search_cli.truncate(result.get("content"), _search_cli.CONTENT_LIMIT),
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
    requirement = _search_cli.BackendRequirementLevel.OPTIONAL
    env_file = _SCRIPT_DIR.parent / ".env"  # this skill's own .env (ADR-0004)
    requirement = _search_cli.BackendRequirementLevel.OPTIONAL
    apply_url = "https://app.tavily.com/home"
    verify_cmd = "python scripts/tavily_search.py check"
    configure_hint = f"pip install tavily-python && export {env_key}=<key> ({apply_url})"
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


def _tavily_extract(client: Any, args: Any) -> dict[str, Any]:
    resp = client.extract(urls=[args.url], extract_depth=args.depth)
    pages = [
        {
            "url": p.get("url", args.url),
            "title": p.get("title", ""),
            "content": _search_cli.truncate(p.get("content"), _search_cli.EXTRACT_CONTENT_LIMIT),
        }
        for p in resp.get("results", [])
    ]
    if not pages:
        # CommandError is non-retryable; the skeleton turns it into the
        # legacy {"error": "no content extracted", "url": ...} + exit 1.
        raise _search_cli.CommandError("no content extracted")
    return pages[0]


def _tavily_add_extract_args(parser: Any) -> None:
    parser.add_argument("url", help="URL to extract")
    parser.add_argument("--depth", choices=["basic", "advanced"], default="advanced", help="Extract depth")


TAVILY_BACKEND = TavilyBackend()
TAVILY_BACKEND.commands = [
    _search_cli.Command(
        "extract",
        "Extract content from a URL",
        _tavily_add_extract_args,
        _tavily_extract,
        managed=True,
        echo=lambda a: {"url": a.url},
    ),
]

try:
    REGISTRY.register(BackendSpec(name="tavily", backend=TAVILY_BACKEND))
except ValueError:
    pass

# Expose global --no-proxy to Exa/Tavily via Registry (expand keeps old JSON shape)
EXA_BACKEND.global_flags = REGISTRY.global_flags  # type: ignore[assignment]
TAVILY_BACKEND.global_flags = REGISTRY.global_flags  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------


def _openalex_abstract(inverted_index: Any) -> str:
    """Rebuild the abstract from OpenAlex's ``{word: [positions]}`` index."""
    if not isinstance(inverted_index, dict):
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for position in positions or []:
            words[position] = word
    return " ".join(words[i] for i in sorted(words))


def _openalex_url(work: dict[str, Any]) -> str:
    """First legal http(s) URL: landing page, then DOI, then the OpenAlex id."""
    landing = (work.get("primary_location") or {}).get("landing_page_url")
    for candidate in (landing, work.get("doi"), work.get("id")):
        if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
            return candidate
    return ""


def _openalex_normalize_work(work: dict[str, Any]) -> dict[str, Any]:
    title = work.get("display_name") or work.get("title") or ""
    snippet = _openalex_abstract(work.get("abstract_inverted_index")) or title
    return {
        "title": title,
        "url": _openalex_url(work),
        "snippet": _search_cli.truncate(snippet, _search_cli.SNIPPET_LIMIT),
        "published_date": work.get("publication_date") or "",
        "score": work.get("relevance_score"),
        "engine_meta": {
            "openalex_id": work.get("id"),
            "doi": work.get("doi"),
            "cited_by_count": work.get("cited_by_count"),
            "is_oa": (work.get("open_access") or {}).get("is_oa"),
        },
    }


OPENALEX_MAX_PER_PAGE = 100  # official `per_page` ceiling


def _openalex_params(query: str, options: dict[str, Any]) -> dict[str, Any]:
    """Map CLI options onto the ``works?search=`` query parameters."""
    params: dict[str, Any] = {"search": query}
    if options.get("num_results") is not None:
        params["per_page"] = max(1, min(int(options["num_results"]), OPENALEX_MAX_PER_PAGE))
    filters: list[str] = []
    if options.get("from_year") is not None:
        filters.append(f"from_publication_date:{int(options['from_year'])}-01-01")
    if options.get("to_year") is not None:
        filters.append(f"to_publication_date:{int(options['to_year'])}-12-31")
    if options.get("open_access"):
        filters.append("is_oa:true")
    if options.get("work_type"):
        filters.append(f"type:{options['work_type']}")
    if filters:
        params["filter"] = ",".join(filters)
    return params


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_HTTP_TIMEOUT = 30.0


class _OpenAlexClient:
    """Plain GET client for ``/works``; identity (key, mailto) is optional."""

    def __init__(self, api_key: str = "", mailto: str = "") -> None:
        self.api_key = api_key
        self.mailto = mailto

    def get_works(self, params: dict[str, Any]) -> dict[str, Any]:
        query = dict(params)
        if self.mailto:
            query["mailto"] = self.mailto
        url = f"{OPENALEX_WORKS_URL}?{urllib.parse.urlencode(query, safe=':,')}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        if self.api_key:
            # Header, not query string: keeps the key out of URLs and logs.
            request.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(request, timeout=OPENALEX_HTTP_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # "HTTP <code>" is the token the shared skeleton classifies on:
            # 429 / 5xx retry, other 4xx fail immediately.
            raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"network error: {exc.reason}") from exc


def _openalex_make_client(api_key: str) -> _OpenAlexClient:
    return _OpenAlexClient(api_key, os.environ.get("OPENALEX_MAILTO", ""))


class OpenAlexBackend(_search_cli.Backend):
    name = "OpenAlex"
    help = "OpenAlex works search CLI for tri-research"
    sdk = urllib.request  # stdlib HTTP is always present: never SdkMissing
    env_key = "OPENALEX_API_KEY"
    env_file = _SCRIPT_DIR.parent / ".env"  # this skill's own .env (ADR-0004)
    requirement = _search_cli.BackendRequirementLevel.OPTIONAL
    apply_url = "https://openalex.org/settings/api"
    verify_cmd = "python scripts/openalex_search.py check"
    configure_hint = f"optional: export {env_key}=<key> ({apply_url})"
    client_factory = staticmethod(_openalex_make_client)
    flags = [
        _search_cli.Flag("num_results", ("--num-results",), "Number of results (default: 5, max 100)", type=int, default=5),
        _search_cli.Flag("from_year", ("--from-year",), "Only works published in or after this year", type=int),
        _search_cli.Flag("to_year", ("--to-year",), "Only works published in or before this year", type=int),
        _search_cli.Flag("open_access", ("--open-access",), "Only open-access works", action="store_true"),
        _search_cli.Flag("work_type", ("--type",), "OpenAlex work type: article, book, dissertation, ..."),
    ]

    def require_setup(self, *, cli_key: str | None = None) -> str:
        """Anonymous is a first-class mode: a missing key resolves to ``""``.

        Only OpenAlex relaxes this; Exa / Tavily / SerpApi keep raising
        ``KeyMissing`` from the shared assembly.
        """
        try:
            return super().require_setup(cli_key=cli_key)
        except _search_cli.KeyMissing:
            return ""

    def probe(self, client: Any) -> bool:
        client.get_works({"search": "test", "per_page": 1})
        return True

    def search(self, client: Any, query: str, options: dict[str, Any]) -> dict[str, Any]:
        resp = client.get_works(_openalex_params(query, options))
        results = [_openalex_normalize_work(w) for w in resp.get("results", [])]
        return {"num_results": len(results), "results": results}


OPENALEX_BACKEND = OpenAlexBackend()

try:
    REGISTRY.register(BackendSpec(name="openalex", backend=OPENALEX_BACKEND))
except ValueError:
    pass  # already registered (module re-imported in tests)

OPENALEX_BACKEND.global_flags = REGISTRY.global_flags  # type: ignore[assignment]

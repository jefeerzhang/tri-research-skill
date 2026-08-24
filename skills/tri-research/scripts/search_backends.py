"""Unified search-backend module for tri-research.

Exa / Tavily / SerpApi backends are declared in one place over the shared
CLI skeleton in `_search_cli.py`. The per-backend CLI scripts
(exa_search.py / tavily_search.py / serpapi_cli.py) remain as thin entry
points so existing callers, sub-agents and tests keep working unchanged.
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

try:
    import exa_py
except ImportError:
    exa_py = None  # type: ignore[assignment]

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore[misc,assignment]

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Exa
# ---------------------------------------------------------------------------

def _exa_normalize_result(result: Any) -> dict[str, Any]:
    return {
        "title": result.title,
        "url": result.url,
        "snippet": (result.text or "")[:500] if hasattr(result, "text") and result.text else "",
        "published_date": str(result.published_date) if hasattr(result, "published_date") and result.published_date else "",
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
    client = EXA_BACKEND.client()
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


def _exa_cmd_contents(args: Any) -> None:
    client = EXA_BACKEND.client()
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
            "results": [_tavily_normalize_result(r) for r in resp.get("results", [])],
        }


def _tavily_cmd_extract(args: Any) -> None:
    client = TAVILY_BACKEND.client()
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


def _tavily_add_extract_args(parser: Any) -> None:
    parser.add_argument("url", help="URL to extract")
    parser.add_argument("--depth", choices=["basic", "advanced"], default="advanced", help="Extract depth")


TAVILY_BACKEND = TavilyBackend()
TAVILY_BACKEND.commands = [
    _search_cli.Command("extract", "Extract content from a URL", _tavily_add_extract_args, _tavily_cmd_extract),
]


# ---------------------------------------------------------------------------
# SerpApi
# ---------------------------------------------------------------------------

SERPAPI_BASE_URL = "https://serpapi.com/search"

SERPAPI_ENGINES = {
    "General": ["google", "bing", "baidu", "duckduckgo", "yahoo", "yandex", "naver", "brave"],
    "Google vertical": ["google_scholar", "google_maps", "google_shopping", "google_news",
                         "google_images", "google_videos", "google_jobs", "google_flights",
                         "google_hotels", "google_finance", "google_patents", "google_play",
                         "google_local", "google_trends", "google_ads", "google_lens",
                         "google_events", "google_related_questions", "google_reverse_image"],
    "Shopping": ["amazon", "walmart", "ebay", "home_depot", "apple_app_store"],
    "Social / Local": ["youtube", "instagram", "facebook", "yelp", "tripadvisor", "opentable"],
}


class SerpApiError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def clear_proxy_vars() -> None:
    """Drop proxy env vars for this process only (opt-in via --no-proxy)."""
    for _p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(_p, None)


def _key_from_env_file(env_path: Path) -> str | None:
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, value = line.partition("=")
                if sep and key.strip() == "SERPAPI_KEY":
                    return value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


def load_key(cli_key: str | None = None) -> str | None:
    if cli_key:
        return cli_key
    env = os.environ.get("SERPAPI_KEY")
    if env:
        return env
    # Try .env in the serpapi skill directory (same as the original CLI).
    serpapi_env = Path(__file__).resolve().parent.parent.parent / "serpapi" / ".env"
    return _key_from_env_file(serpapi_env)


def build_tbs(since: str | None) -> str | None:
    """Translate a human time window into Google's tbs parameter."""
    if not since:
        return None
    s = since.strip().lower()
    unit_map = {"h": "h", "d": "d", "w": "w", "m": "m", "y": "y"}
    if s in unit_map:
        return f"qdr:{unit_map[s]}"
    if len(s) >= 2 and s[-1] in unit_map and s[:-1].isdigit():
        return f"qdr:{s[:-1]}{unit_map[s[-1]]}"
    if "-" in s:
        parts = s.split("-")
        if len(parts) == 2 and all(p.isdigit() and len(p) == 4 for p in parts):
            y1, y2 = parts
            return f"cdr:1,cd_min:{y1}-01-01,cd_max:{y2}-12-31"
    if s.isdigit() and len(s) == 4:
        return f"cdr:1,cd_min:{s}-01-01,cd_max:{s}-12-31"
    return None


def _serpapi_fetch(
    engine: str,
    query: str,
    hl: str | None,
    gl: str | None,
    num: int | None,
    api_key: str,
    since: str | None = None,
) -> dict[str, Any]:
    """Return parsed SerpApi JSON; raise SerpApiError with a CLI exit code."""
    if requests is None:
        raise SerpApiError("Missing dependency: requests. Install with: pip install requests", 2)
    if not api_key:
        raise SerpApiError(
            "No SerpApi key found. Set SERPAPI_KEY env var, add it to .env "
            "(SERPAPI_KEY=...), or pass --api_key.\n"
            "Get a free key at https://serpapi.com/dashboard",
            1,
        )
    params: dict[str, Any] = {"engine": engine, "q": query, "api_key": api_key, "output": "json"}
    if hl:
        params["hl"] = hl
    if gl:
        params["gl"] = gl
    if num:
        params["num"] = num
    tbs = build_tbs(since)
    if tbs:
        params["tbs"] = tbs

    try:
        r = requests.get(SERPAPI_BASE_URL, params=params, timeout=60)
    except requests.exceptions.SSLError as e:
        raise SerpApiError(
            f"SSL error: {e}\nIf behind a proxy, retry with --no-proxy "
            f"(clears HTTP_PROXY/HTTPS_PROXY for this run).\n",
            3,
        ) from e
    except requests.exceptions.RequestException as e:
        raise SerpApiError(f"Network error: {e}\n", 3) from e

    if r.status_code != 200:
        raise SerpApiError(f"HTTP {r.status_code}: {r.text[:500]}\n", 4)
    data = r.json()
    if "error" in data:
        raise SerpApiError(f"SerpApi error: {data['error']}\n", 5)
    return data


def _serpapi_fetch_cli(engine, query, hl, gl, num, api_key, since=None) -> dict[str, Any]:
    """CLI-facing fetch that preserves the original SerpApi exit codes."""
    try:
        return _serpapi_fetch(engine, query, hl, gl, num, api_key, since)
    except SerpApiError as exc:
        sys.stderr.write(str(exc) + "\n")
        sys.exit(exc.exit_code)


class _SerpApiClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


def _serpapi_make_client(api_key: str) -> _SerpApiClient:
    return _SerpApiClient(api_key)


def _serpapi_print_human(data: dict[str, Any]) -> None:
    organic = data.get("organic_results", [])
    if not organic:
        print("No organic results returned. (try a different query/engine)")
        if data.get("answer_box") or data.get("knowledge_graph"):
            print("Note: an answer box / knowledge graph was returned.")
        return
    for i, res in enumerate(organic, 1):
        print(f"{i}. {res.get('title', '(no title)')}")
        print(f"   {res.get('link', '')}")
        snippet = res.get("snippet", "")
        if snippet:
            print(f"   {snippet}")
        print()


def _serpapi_cmd_search(backend: Any, args: Any) -> None:
    if getattr(args, "no_proxy", False):
        clear_proxy_vars()
    api_key = load_key(args.api_key)
    data = _serpapi_fetch_cli(args.engine, args.query, args.hl, args.gl, args.num, api_key, args.since)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        _serpapi_print_human(data)


def _serpapi_cmd_batch_search(backend: Any, args: Any) -> None:
    if getattr(args, "no_proxy", False):
        clear_proxy_vars()
    api_key = load_key(args.api_key)
    # Per-query value is always an object: {"results": [...]} on success,
    # {"error": "..."} on failure — consumers never need type-switching.
    # This also matches what the generic _search_cli batch path emits for
    # Exa/Tavily ({"results": [...]}).
    all_results: dict[str, Any] = {}
    for query in args.query:
        try:
            data = _serpapi_fetch(
                args.engine, query, args.hl, args.gl, args.num, api_key, args.since
            )
            all_results[query] = {"results": data.get("organic_results", [])}
        except SerpApiError as exc:
            all_results[query] = {"error": str(exc)}
    print(json.dumps(all_results, ensure_ascii=False))


def _serpapi_cmd_export(args: Any) -> None:
    if getattr(args, "no_proxy", False):
        clear_proxy_vars()
    api_key = load_key(args.api_key)
    data = _serpapi_fetch_cli(args.engine, args.query, args.hl, args.gl, args.num, api_key, args.since)
    organic = data.get("organic_results", [])
    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append(f"# {args.query} - 检索结果")
    lines.append("")
    lines.append(f"- 检索时间: {ts}")
    lines.append(f"- 引擎: {args.engine}" + (f" (hl={args.hl}, gl={args.gl})" if args.hl or args.gl else ""))
    lines.append(f"- 结果数: {len(organic)}")
    lines.append("")
    for i, x in enumerate(organic, 1):
        lines.append(f"## {i}. {x.get('title', '')}")
        lines.append(f"- 链接: {x.get('link', '')}")
        sn = x.get("snippet", "")
        if sn:
            lines.append(f"- 摘要: {sn}")
        lines.append("")

    out_path = args.out
    if not out_path:
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in args.query)
        # Look for an existing project-level data/ dir near the skill;
        # when none is found, fall back to the CURRENT directory instead of
        # walking all the way to the filesystem root and creating
        # <drive>/data/output there.
        here = os.path.dirname(os.path.abspath(__file__))
        root = None
        candidate = here
        for _ in range(5):
            if os.path.isdir(os.path.join(candidate, "data")):
                root = candidate
                break
            parent = os.path.dirname(candidate)
            if parent == candidate:
                break
            candidate = parent
        if root is None:
            root = os.getcwd()
        out_dir = os.path.join(root, "data", "output")
        out_path = os.path.join(out_dir, f"{safe}_检索结果.md")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"saved {out_path} ({len(organic)} results)")


def _serpapi_cmd_doc(args: Any) -> None:
    print("""SerpApi CLI wrapper.

Usage:
  python serpapi_cli.py doc
  python serpapi_cli.py engines
  python serpapi_cli.py search --query "KEYWORD" [--engine google] [--hl zh-cn] [--gl cn] [--num 10] [--json] [--api_key KEY]
  python serpapi_cli.py search --query "KEYWORD" --no-proxy
""")


def _serpapi_cmd_engines(args: Any) -> None:
    for cat, items in SERPAPI_ENGINES.items():
        print(f"## {cat}")
        for e in items:
            print(f"  - {e}")
        print()


def _serpapi_add_common_search_args(parser: Any) -> None:
    parser.add_argument("--engine", "-e", default="google", help="Engine (default: google)")
    parser.add_argument("--hl", default=None, help="Host language, e.g. zh-cn")
    parser.add_argument("--gl", default=None, help="Geolocation, e.g. cn")
    parser.add_argument("--num", "-n", type=int, default=None, help="Number of results")
    parser.add_argument("--since", default=None, help="Time window: h/d/w/m/y, N+y (e.g. 5y), or YYYY / YYYY-YYYY")
    parser.add_argument("--api_key", default=None, help="SerpApi API key")


def _serpapi_add_search_args(parser: Any) -> None:
    parser.add_argument("--query", "-q", required=True, help="Search keyword")
    _serpapi_add_common_search_args(parser)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")


def _serpapi_add_batch_args(parser: Any) -> None:
    parser.add_argument("--query", action="append", required=True, help="Query (can repeat)")
    _serpapi_add_common_search_args(parser)


def _serpapi_add_export_args(parser: Any) -> None:
    parser.add_argument("--query", "-q", required=True, help="Search keyword")
    _serpapi_add_common_search_args(parser)
    parser.add_argument("--out", "-o", default=None, help="Output path (default: data/output/<query>_检索结果.md)")


class SerpApiBackend(_search_cli.Backend):
    name = "SerpApi"
    help = "SerpApi CLI for tri-research"
    sdk = requests
    missing_sdk_message = "requests not installed"
    env_key = "SERPAPI_KEY"
    client_factory = staticmethod(_serpapi_make_client)
    global_flags = [
        _search_cli.Flag("no_proxy", ("--no-proxy",), "Clear proxy env vars for this run", action="store_true"),
    ]
    search_handler = staticmethod(_serpapi_cmd_search)
    batch_search_handler = staticmethod(_serpapi_cmd_batch_search)
    search_args_builder = staticmethod(_serpapi_add_search_args)
    batch_search_args_builder = staticmethod(_serpapi_add_batch_args)

    def probe(self, client: Any) -> bool:
        _serpapi_fetch("google", "test", None, None, 1, client.api_key)
        return True

    def search(self, client: Any, query: str, options: dict[str, Any]) -> dict[str, Any]:
        data = _serpapi_fetch(
            options.get("engine", "google"),
            query,
            options.get("hl"),
            options.get("gl"),
            options.get("num"),
            client.api_key,
            options.get("since"),
        )
        return {"results": data.get("organic_results", [])}


SERPAPI_BACKEND = SerpApiBackend()
SERPAPI_BACKEND.commands = [
    _search_cli.Command("doc", "Print full interface spec", lambda p: None, _serpapi_cmd_doc),
    _search_cli.Command("engines", "List supported engines", lambda p: None, _serpapi_cmd_engines),
    _search_cli.Command("export", "Run a search and save as Markdown file", _serpapi_add_export_args, _serpapi_cmd_export),
]

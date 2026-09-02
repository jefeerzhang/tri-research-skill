#!/usr/bin/env python3
"""SerpApi CLI wrapper for tri-research.

Self-contained: declares the SerpApi backend, key-loading helpers, proxy
handling, fetch client, and all five commands (search / check /
batch_search / doc / engines / export) here. Lives next to the wrapper
(rather than in `tri-research/scripts/search_backends.py`) so the shared
search-backend module stays symmetric across the Exa / Tavily / SerpApi
shape — SerpApi's extra commands and key/proxy plumbing would otherwise
dominate that module and obscure the Exa + Tavily skeleton.

External command path (`python serpapi_cli.py search ...`) and JSON
output shape are unchanged from 6.5.0; existing callers, sub-agents and
tests keep working.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

# Make the tri-research `_search_cli` skeleton importable regardless of cwd.
_TRI_RESEARCH_SCRIPTS = Path(__file__).resolve().parents[2] / "tri-research" / "scripts"
if str(_TRI_RESEARCH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TRI_RESEARCH_SCRIPTS))

import _search_cli  # noqa: E402

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


SERPAPI_BASE_URL = "https://serpapi.com/search"

SERPAPI_ENGINES = {
    "General": ["google", "bing", "baidu", "duckduckgo", "yahoo", "yandex", "naver", "brave"],
    "Google vertical": [
        "google_scholar",
        "google_maps",
        "google_shopping",
        "google_news",
        "google_images",
        "google_videos",
        "google_jobs",
        "google_flights",
        "google_hotels",
        "google_finance",
        "google_patents",
        "google_play",
        "google_local",
        "google_trends",
        "google_ads",
        "google_lens",
        "google_events",
        "google_related_questions",
        "google_reverse_image",
    ],
    "Shopping": ["amazon", "walmart", "ebay", "home_depot", "apple_app_store"],
    "Social / Local": ["youtube", "instagram", "facebook", "yelp", "tripadvisor", "opentable"],
}


class SerpApiError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def load_key(cli_key: str | None = None) -> str | None:
    """Resolve via KeyProvider (cli > env > this skill's .env), like Exa/Tavily.

    The historical ImportError fallback + local `_key_from_env_file` copy
    are gone: unreachable (the top-level `_search_cli` import above shares
    its directory with `_search_registry`), same rationale as ADR-0002.
    """
    from _search_registry import KeyProvider  # noqa: E402 — deferred like _backend_api_key

    return KeyProvider.resolve(cli_key, "SERPAPI_KEY", Path(__file__).resolve().parents[1] / ".env")


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
    timeout: int = 60,
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
        r = requests.get(SERPAPI_BASE_URL, params=params, timeout=timeout)
    except requests.exceptions.SSLError as e:
        raise SerpApiError(
            f"SSL error: {e}\nIf behind a proxy, retry with --no-proxy (clears HTTP_PROXY/HTTPS_PROXY for this run).\n",
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


def _serpapi_invoke_fetch(
    backend: Any,
    engine: str,
    query: str,
    hl: str | None,
    gl: str | None,
    num: int | None,
    api_key: str,
    since: str | None,
) -> dict[str, Any]:
    timeout = int(backend.call_timeout or 60)
    return _search_cli.invoke(
        backend,
        lambda: _serpapi_fetch(engine, query, hl, gl, num, api_key, since, timeout=timeout),
    )


def _serpapi_fetch_cli(engine, query, hl, gl, num, api_key, since=None, *, backend: Any) -> dict[str, Any]:
    """CLI-facing fetch through invoke(), preserving SerpApi exit codes."""
    try:
        return _serpapi_invoke_fetch(backend, engine, query, hl, gl, num, api_key, since)
    except SerpApiError as exc:
        sys.stderr.write(str(exc) + "\n")
        sys.exit(exc.exit_code)
    except Exception as exc:
        sys.stderr.write(str(exc) + "\n")
        sys.exit(3)


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
        _search_cli.clear_proxy_vars()
    api_key = load_key(args.api_key)
    data = _serpapi_fetch_cli(args.engine, args.query, args.hl, args.gl, args.num, api_key, args.since, backend=backend)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        _serpapi_print_human(data)


def _serpapi_cmd_batch_search(backend: Any, args: Any) -> None:
    if getattr(args, "no_proxy", False):
        _search_cli.clear_proxy_vars()
    api_key = load_key(args.api_key)
    # SerpApi's per-query value is always an object: {"results": [...]} on
    # success, {"error": "..."} on failure — consumers of THIS CLI never need
    # type-switching. This does NOT match the generic _search_cli batch path
    # (Exa/Tavily), which unwraps to a BARE list per query
    # (`output.get("results", [])`). The two CLIs' batch shapes differ, so a
    # consumer spanning both must handle list vs {"results": [...]}.
    all_results: dict[str, Any] = {}
    for query in args.query:
        try:
            data = _serpapi_invoke_fetch(
                backend,
                args.engine,
                query,
                args.hl,
                args.gl,
                args.num,
                api_key,
                args.since,
            )
            all_results[query] = {"results": data.get("organic_results", [])}
        except Exception as exc:
            all_results[query] = {"error": str(exc)}
    print(json.dumps(all_results, ensure_ascii=False))


def _serpapi_cmd_export(args: Any) -> None:
    if getattr(args, "no_proxy", False):
        _search_cli.clear_proxy_vars()
    api_key = load_key(args.api_key)
    data = _serpapi_fetch_cli(
        args.engine, args.query, args.hl, args.gl, args.num, api_key, args.since, backend=SERPAPI_BACKEND
    )
    organic = data.get("organic_results", [])
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
    # This skill's own .env, declared here so KeyProvider needs no layout
    # knowledge (ADR-0004) — matches load_key's env_file below.
    env_file = Path(__file__).resolve().parents[1] / ".env"
    client_factory = staticmethod(_serpapi_make_client)
    call_timeout = 60.0
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
            # Derive the requests timeout from call_timeout — the same single
            # knob the CLI path (_serpapi_invoke_fetch) uses. Without this the
            # Registry path (which calls backend.search) fell back to
            # _serpapi_fetch's hardcoded default 60 and diverged from the CLI.
            timeout=int(self.call_timeout or 60),
        )
        return {"results": data.get("organic_results", [])}


SERPAPI_BACKEND = SerpApiBackend()
SERPAPI_BACKEND.commands = [
    _search_cli.Command("doc", "Print full interface spec", lambda p: None, _serpapi_cmd_doc),
    _search_cli.Command("engines", "List supported engines", lambda p: None, _serpapi_cmd_engines),
    _search_cli.Command(
        "export", "Run a search and save as Markdown file", _serpapi_add_export_args, _serpapi_cmd_export
    ),
]


def main(argv: list[str] | None = None) -> int:
    return _search_cli.run(SERPAPI_BACKEND, argv)


# Register with global Registry so new callers can use REGISTRY.search("serpapi", ...)
try:
    from _search_registry import REGISTRY, BackendSpec  # noqa: E402

    REGISTRY.register(BackendSpec(name="serpapi", backend=SERPAPI_BACKEND, env_key="SERPAPI_KEY"))
except (ImportError, ValueError):
    pass


if __name__ == "__main__":
    raise SystemExit(main())

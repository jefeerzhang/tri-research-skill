#!/usr/bin/env python3
"""SerpApi CLI wrapper.

Usage:
  python serpapi_cli.py doc
  python serpapi_cli.py engines
  python serpapi_cli.py search --query "KEYWORD" [--engine google] [--hl zh-cn] [--gl cn] [--num 10] [--json] [--api_key KEY]

Environment note: this machine's HTTP proxy breaks HTTPS to serpapi.com.
We clear HTTP_PROXY/HTTPS_PROXY before every request automatically.
"""
import argparse
import json
import os
import sys

try:
    import requests
except ImportError:
    sys.stderr.write("Missing dependency: requests. Install with: pip install requests\n")
    sys.exit(2)

BASE_URL = "https://serpapi.com/search"

# Clear proxy vars that break the SSL handshake on this machine.
for _p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_p, None)


def load_key(cli_key=None):
    if cli_key:
        return cli_key
    env = os.environ.get("SERPAPI_KEY")
    if env:
        return env
    # Try .env in skill dir
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("SERPAPI_KEY"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


ENGINES = {
    "General": ["google", "bing", "baidu", "duckduckgo", "yahoo", "yandex", "naver", "brave"],
    "Google vertical": ["google_scholar", "google_maps", "google_shopping", "google_news",
                         "google_images", "google_videos", "google_jobs", "google_flights",
                         "google_hotels", "google_finance", "google_patents", "google_play",
                         "google_local", "google_trends", "google_ads", "google_lens",
                         "google_events", "google_related_questions", "google_reverse_image"],
    "Shopping": ["amazon", "walmart", "ebay", "home_depot", "apple_app_store"],
    "Social / Local": ["youtube", "instagram", "facebook", "yelp", "tripadvisor", "opentable"],
}


def cmd_doc():
    print(__doc__)


def cmd_engines():
    for cat, items in ENGINES.items():
        print(f"## {cat}")
        for e in items:
            print(f"  - {e}")
        print()


def build_tbs(since):
    """Translate a human time window into Google's tbs parameter.

    Accepts:
      h / d / w / m / y          -> qdr:<x> (past hour/day/week/month/year)
      Nh / Nd / Nw / Nm / Ny     -> qdr:<x> with count, e.g. 5y -> qdr:5y
      YYYY | YYYY-YYYY           -> custom date range cdr:1,cd_min..,cd_max..
    Returns the tbs string or None if no filter.
    """
    if not since:
        return None
    s = since.strip().lower()
    unit_map = {"h": "h", "d": "d", "w": "w", "m": "m", "y": "y"}
    if s in unit_map:
        return f"qdr:{unit_map[s]}"
    # N + unit, e.g. 5y, 12m
    if len(s) >= 2 and s[-1] in unit_map and s[:-1].isdigit():
        return f"qdr:{s[:-1]}{unit_map[s[-1]]}"
    # single year or year range
    if "-" in s:
        parts = s.split("-")
        if len(parts) == 2 and all(p.isdigit() and len(p) == 4 for p in parts):
            y1, y2 = parts
            return f"cdr:1,cd_min:{y1}-01-01,cd_max:{y2}-12-31"
    if s.isdigit() and len(s) == 4:
        return f"cdr:1,cd_min:{s}-01-01,cd_max:{s}-12-31"
    return None


def fetch(engine, query, hl, gl, num, api_key, since=None):
    """Core fetch: returns parsed JSON dict or exits with an error code."""
    key = load_key(api_key)
    if not key:
        sys.stderr.write(
            "No SerpApi key found. Set SERPAPI_KEY env var, add it to .env "
            "(SERPAPI_KEY=...), or pass --api_key.\n"
            "Get a free key at https://serpapi.com/dashboard\n"
        )
        sys.exit(1)

    params = {"engine": engine, "q": query, "api_key": key, "output": "json"}
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
        r = requests.get(BASE_URL, params=params, timeout=60)
    except requests.exceptions.SSLError as e:
        sys.stderr.write(
            f"SSL error: {e}\nIf behind a proxy, clear HTTP_PROXY/HTTPS_PROXY env vars.\n"
        )
        sys.exit(3)
    except requests.exceptions.RequestException as e:
        sys.stderr.write(f"Network error: {e}\n")
        sys.exit(3)

    if r.status_code != 200:
        sys.stderr.write(f"HTTP {r.status_code}: {r.text[:500]}\n")
        sys.exit(4)

    data = r.json()

    if "error" in data:
        sys.stderr.write(f"SerpApi error: {data['error']}\n")
        sys.exit(5)

    return data


def run_search(engine, query, hl, gl, num, as_json, api_key, since=None):
    data = fetch(engine, query, hl, gl, num, api_key, since)

    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    # Human-readable summary
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


def run_export(engine, query, hl, gl, num, out_path, api_key, since=None):
    import datetime
    data = fetch(engine, query, hl, gl, num, api_key, since)
    organic = data.get("organic_results", [])
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append(f"# {query} - 检索结果")
    lines.append("")
    lines.append(f"- 检索时间: {ts}")
    lines.append(f"- 引擎: {engine}" + (f" (hl={hl}, gl={gl})" if hl or gl else ""))
    lines.append(f"- 结果数: {len(organic)}")
    lines.append("")
    for i, x in enumerate(organic, 1):
        lines.append(f"## {i}. {x.get('title', '')}")
        lines.append(f"- 链接: {x.get('link', '')}")
        sn = x.get("snippet", "")
        if sn:
            lines.append(f"- 摘要: {sn}")
        lines.append("")

    if not out_path:
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in query)
        # Default to the workspace-root data/output, not the current working dir,
        # so exports land in a stable place regardless of where the CLI is invoked.
        # Walk up from this script until we find a directory that has a data/ folder
        # (the workspace root), falling back to three levels up.
        here = os.path.dirname(os.path.abspath(__file__))
        root = here
        for _ in range(5):
            if os.path.isdir(os.path.join(root, "data")):
                break
            parent = os.path.dirname(root)
            if parent == root:
                break
            root = parent
        out_dir = os.path.join(root, "data", "output")
        out_path = os.path.join(out_dir, f"{safe}_检索结果.md")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"saved {out_path} ({len(organic)} results)")


def main():
    parser = argparse.ArgumentParser(description="SerpApi CLI wrapper")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("doc", help="Print full interface spec")
    sub.add_parser("engines", help="List supported engines")

    p_search = sub.add_parser("search", help="Run a search (print results)")
    p_search.add_argument("--query", "-q", required=True, help="Search keyword")
    p_search.add_argument("--engine", "-e", default="google", help="Engine (default: google)")
    p_search.add_argument("--hl", default=None, help="Host language, e.g. zh-cn")
    p_search.add_argument("--gl", default=None, help="Geolocation, e.g. cn")
    p_search.add_argument("--num", "-n", type=int, default=None, help="Number of results")
    p_search.add_argument("--since", default=None, help="Time window: h/d/w/m/y, N+y (e.g. 5y), or YYYY / YYYY-YYYY")
    p_search.add_argument("--json", action="store_true", help="Output raw JSON")
    p_search.add_argument("--api_key", default=None, help="SerpApi API key")

    p_export = sub.add_parser("export", help="Run a search and save as Markdown file")
    p_export.add_argument("--query", "-q", required=True, help="Search keyword")
    p_export.add_argument("--engine", "-e", default="google", help="Engine (default: google)")
    p_export.add_argument("--hl", default=None, help="Host language, e.g. zh-cn")
    p_export.add_argument("--gl", default=None, help="Geolocation, e.g. cn")
    p_export.add_argument("--num", "-n", type=int, default=None, help="Number of results")
    p_export.add_argument("--since", default=None, help="Time window: h/d/w/m/y, N+y (e.g. 5y), or YYYY / YYYY-YYYY")
    p_export.add_argument("--out", "-o", default=None, help="Output path (default: data/output/<query>_检索结果.md)")
    p_export.add_argument("--api_key", default=None, help="SerpApi API key")

    args = parser.parse_args()
    if args.cmd == "doc":
        cmd_doc()
    elif args.cmd == "engines":
        cmd_engines()
    elif args.cmd == "search":
        run_search(args.engine, args.query, args.hl, args.gl, args.num, args.json, args.api_key, args.since)
    elif args.cmd == "export":
        run_export(args.engine, args.query, args.hl, args.gl, args.num, args.out, args.api_key, args.since)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

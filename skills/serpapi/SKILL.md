---
name: serpapi
description: Scrape Google and 100+ search engines (Bing, Baidu, DuckDuckGo, YouTube, Amazon, Google Scholar, Maps, Flights, etc.) as structured JSON via the SerpApi real-time API. Use when the user wants real search-engine results, SERP data, competitor/SEO monitoring, price tracking, or any task that needs search output without writing a scraper. Also trigger when the user mentions SerpApi, "搜索API", "抓取谷歌", or wants real Google results in JSON.
version: 1.0.0
authors:
  - testclaw
credentials:
  - name: SERPAPI_KEY
    required: true
    description: "SerpApi API key from https://serpapi.com/dashboard (free tier: 250 searches/month)."
    storage: ".env file in skill dir, SERPAPI_KEY env var, or --api_key CLI flag"
---

## Overview

SerpApi returns structured JSON for Google and 100+ other search engines, handling proxies, CAPTCHAs, and geolocation so you get what a human sees. This skill wraps a cross-platform CLI for `https://serpapi.com/search`.

## When to use

- Real Google/Bing/Baidu/DuckDuckGo/Yahoo/Yandex results as structured data
- Vertical SERPs: Maps, Local, Shopping, Jobs, Scholar, News, Images, Videos, Flights, Hotels, Finance, Patents, Play Store, YouTube transcripts
- Competitor/SEO monitoring, price tracking, review scraping, ad intelligence
- Any task where a hand-written scraper would be needed but an API is cleaner

**Default provider? No.** SerpApi is a supplement: when unavailable (no key, quota exhausted, network error), report it and fall back to other available search methods — never a silent interchange.

## API key

Priority: `--api_key` flag > `.env` file (`SERPAPI_KEY`) > environment variable.

Guide the user in their language: register at <https://serpapi.com> (free, 250 searches/month, no credit card) → Dashboard → API Key → save to `<skill_dir>/.env` as `SERPAPI_KEY=...` or export the env var. Don't paste keys in chat — store them in `.env` instead.

| Scenario          | Behavior                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------ |
| No key            | Refuse to run; show the setup guide.                                                                   |
| Invalid key       | API returns `{"error": "API key not valid..."}`; report and ask the user to recheck.                   |
| Quota exhausted   | API returns `{"error": "Your search limit is exhausted..."}`; inform user, suggest upgrading.          |
| Network/SSL error | Usually a proxy issue — retry with `--no-proxy` (clears `HTTP_PROXY`/`HTTPS_PROXY` for that run only). |

## CLI

`python <skill_dir>/scripts/serpapi_cli.py <command> [options]` — run `doc` first for the offline usage summary.

- `doc` — print usage summary (offline).
- `check` — availability probe: SDK + key + one live 1-result query; always prints JSON (`{"available": true|false, "error": "..."}`), never a traceback.
- `search --engine google --query "KEYWORD" [--hl zh-cn] [--gl cn] [--num 10] [--json] [--api_key KEY]` — run a search (print to stdout).
- `batch_search --query "Q1" --query "Q2" [--engine ...] [--hl ...] [--gl ...] [--num ...] [--since ...]` — run multiple queries sequentially; output maps each query to `{"results": [...]}` on success, `{"error": "..."}` on failure.
- `export --query "KEYWORD" [--hl zh-cn] [--gl cn] [--num 10] [--out path.md]` — run a search and save as a Markdown file (default: `data/output/<query>_检索结果.md`).
- `engines` — list supported engines.

### Examples

```text
python serpapi_cli.py check
python serpapi_cli.py search --query "OpenAI" --num 5
python serpapi_cli.py search --engine google --query "北京天气" --hl zh-cn --gl cn
python serpapi_cli.py search --engine google_scholar --query "transformer attention"
python serpapi_cli.py search --query "python" --json > out.json
python serpapi_cli.py batch_search --query "人工智能 就业" --query "AI job displacement" --num 5
python serpapi_cli.py export --query "资产搁浅风险" --hl zh-cn --gl cn --num 10
python serpapi_cli.py export --query "stranded assets" --out ./report.md
```

### Output

- `search` (default): readable list (position, title, link, snippet); with `--json`: raw SerpApi JSON.
- `export`: writes a Markdown report with title/link/snippet per result, auto-creating the output directory.

**Proxy note:** if a proxy environment variable (`HTTP_PROXY`/`HTTPS_PROXY`) breaks the HTTPS handshake to `serpapi.com` (e.g. `SSL: UNEXPECTED_EOF_WHILE_READING`), pass `--no-proxy` before the subcommand — the CLI clears those variables for that run only, and never mutates the environment otherwise.

## Supported engines (subset)

google, google_scholar, bing, baidu, duckduckgo, yahoo, yandex, youtube, amazon,
google_maps, google_shopping, google_news, google_images, google_jobs, google_flights,
google_hotels, google_finance, google_patents, google_play, google_local, google_trends,
walmart, ebay, apple_app_store, instagram, yelp, tripadvisor, facebook, naver, brave.
Run `engines` for the full categorized list.

## Safety

- Only GET to `https://serpapi.com/search`; never write or modify external data.
- Never delete or overwrite user files; `export` only creates/appends under `data/output/`.
- Keys are read via `SERPAPI_KEY` (env or `.env`) or `--api_key` only — never written to logs or stdout.
- Not the default search provider: when unavailable, stop and report — don't silently substitute other search methods.
- Queries go to SerpApi and bill quota per call — avoid sending private or sensitive content in queries.

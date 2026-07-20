---
name: serpapi
description: Scrape Google and 100+ other search engines (Bing, Baidu, DuckDuckGo, YouTube, Amazon, Google Scholar, Maps, Flights, etc.) via the SerpApi real-time JSON API. Use when the user wants structured search-engine results, SERP data, competitor/SEO monitoring, price tracking, or any task that needs real search-engine output without writing a scraper. Also trigger when the user mentions SerpApi, "搜索API", "抓取谷歌", or wants real Google results in JSON.
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

SerpApi is a real-time API that returns structured JSON for Google and 100+ other
search engines. It handles proxies, CAPTCHA solving, and global geolocation so you
get exactly what a human sees. This skill bundles a cross-platform CLI that wraps
`https://serpapi.com/search`.

**Hard environment note (this machine):** an HTTP proxy breaks the HTTPS handshake
to `serpapi.com` (`SSL: UNEXPECTED_EOF_WHILE_READING`). The bundled CLI auto-clears
`HTTP_PROXY`/`HTTPS_PROXY` before every request. If you call the API directly, you
MUST `os.environ.pop("HTTP_PROXY"); os.environ.pop("HTTPS_PROXY")` first.

## Trigger

Activate this skill when the user needs:
1. Real Google/Bing/Baidu/DuckDuckGo/Yahoo/Yandex search results as structured data.
2. Vertical SERP data: Google Maps, Local, Shopping, Jobs, Scholar, News, Images,
   Videos, Flights, Hotels, Finance, Patents, Play Store, YouTube transcripts, etc.
3. Competitor/SEO monitoring, price tracking, review scraping, ad intelligence.
4. Any task where a hand-written scraper would be needed but an API is cleaner.

**Rule:** Do not be the exclusive search provider. When SerpApi is unavailable
(no key, quota exhausted, network error), inform the user and fall back to other
available search methods.

## Recommended Entry Point

Run the CLI `doc` command for the full interface spec (offline, no network):

| Runtime | Command |
|---------|---------|
| Python | `python <skill_dir>/scripts/serpapi_cli.py doc` |
| PowerShell | `powershell -ExecutionPolicy Bypass -File <skill_dir>/scripts/serpapi_cli.py doc` |

## API Key Management

### Key source priority
```
--api_key CLI flag  >  .env file (SERPAPI_KEY)  >  system environment variable
```

### How to get a key (guide the user in their language)
> **SerpApi API Key setup**
> 1. Go to https://serpapi.com/ and click **Register** (free, no credit card, 250 searches/month).
> 2. After login, open the **Dashboard → API Key** page. Copy the key.
> 3. Save it to `<skill_dir>/.env`: `SERPAPI_KEY=<your_key_here>`
>    or set the env var: `$env:SERPAPI_KEY="<your_key_here>"`
>
> For security, avoid pasting keys directly in chat. Store them in `.env` instead.

### Quota / error handling
| Scenario | Behavior |
|----------|----------|
| No key | Refuse to run; show the setup guide above. |
| Invalid key | API returns `{"error": "API key not valid..."}`. Report and ask user to recheck key. |
| Quota exhausted | API returns `{"error": "Your search limit is exhausted..."}`. Inform user, suggest upgrading plan. |
| Network/SSL error | Usually the proxy issue — the CLI auto-clears proxy vars; if calling directly, clear them manually. |

## CLI Usage

| Runtime | Invocation |
|---------|-----------|
| Python | `python <skill_dir>/scripts/serpapi_cli.py <command> [options]` |

### Commands
- `doc` — print full interface spec (offline).
- `search --engine google --query "KEYWORD" [--hl zh-cn] [--gl cn] [--num 10] [--json]` — run a search (print to stdout).
- `export --query "KEYWORD" [--hl zh-cn] [--gl cn] [--num 10] [--out path.md]` — run a search and save as a Markdown file (default: `data/output/<query>_检索结果.md`).
- `engines` — list supported engines.

### Examples
```
python serpapi_cli.py search --query "OpenAI" --num 5
python serpapi_cli.py search --engine google --query "北京天气" --hl zh-cn --gl cn
python serpapi_cli.py search --engine google_scholar --query "transformer attention"
python serpapi_cli.py search --query "python" --json > out.json
python serpapi_cli.py export --query "资产搁浅风险" --hl zh-cn --gl cn --num 10
python serpapi_cli.py export --query "stranded assets" --out ./report.md
```

### Output
- `search` (default): readable list (position, title, link, snippet). With `--json`: raw SerpApi JSON.
- `export`: writes a Markdown report with title/link/snippet per result, auto-creating the output directory.

## 安全边界
- 只向 `https://serpapi.com/search` 发 GET 请求，不写、不改任何外部数据。
- 不删除、不覆盖用户文件；`export` 只新建/追加 `data/output/` 下的文件。
- 不收集密钥：key 仅从 `SERPAPI_KEY` 环境变量或 `--api_key` 读取，绝不写入日志或 stdout。
- 不是默认搜索源：SerpApi 不可用时停止并报错，不静默替代其他搜索方式。
- 查询内容会发送至 SerpApi 并触发计费（按次扣额度），避免用其查询含敏感信息的私密内容。

## Supported engines (subset)
google, google_scholar, bing, baidu, duckduckgo, yahoo, yandex, youtube, amazon,
google_maps, google_shopping, google_news, google_images, google_jobs, google_flights,
google_hotels, google_finance, google_patents, google_play, google_local, google_trends,
walmart, ebay, apple_app_store, instagram, yelp, tripadvisor, facebook, naver, brave.
Run `engines` for the full categorized list.

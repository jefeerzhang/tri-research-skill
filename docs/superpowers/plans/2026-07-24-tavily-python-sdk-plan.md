# Tavily Python SDK 改造实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 `skills/tri-research` 主代理的 Tavily 调用方式从 MCP 改为 Python SDK，新增 `scripts/tavily_search.py` 封装脚本，同步更新文档与测试，子代理保持原设计不变。

**架构：** 仿照现有 `scripts/exa_search.py`，新增 `scripts/tavily_search.py` 作为 `tavily-python` SDK 的 CLI 包装；主代理通过 Bash 调用该脚本完成 Tavily 搜索/提取，输出统一 JSON。文档（`SKILL.md`、`README.md`、`runtime-adapters.md`）同步移除 MCP 描述，改为 Python SDK 调用示例。

**技术栈：** Python 3.x、`tavily-python`、`argparse`、`json`、标准库 `unittest`。

---

## 文件结构

| 文件 | 职责 | 操作 |
|---|---|---|
| `skills/tri-research/scripts/tavily_search.py` | Tavily Python SDK 的 CLI 包装，提供 search / batch_search / extract / check | 创建 |
| `skills/tri-research/tests/test_tavily_search.py` | `tavily_search.py` 的单元测试，覆盖解析、输出结构、错误处理 | 创建 |
| `skills/tri-research/SKILL.md` | 更新 Tavily 调用规范为 Python SDK | 修改 |
| `skills/tri-research/references/runtime-adapters.md` | 更新适配表中 Tavily 的实现方式 | 修改 |
| `skills/tri-research/README.md` | 更新 Tavily 安装与调用说明 | 修改 |
| `skills/tri-research/CHANGELOG.md` | 记录 Tavily 调用方式变更 | 修改 |
| `skills/tri-research/tests/test_skill_contract.py` | 现有契约测试，验证后不应被破坏 | 只读验证 |

---

### 任务 1：创建 `scripts/tavily_search.py` 基础框架

**文件：**
- 创建：`skills/tri-research/scripts/tavily_search.py`

- [ ] **步骤 1：编写脚本骨架与 `check` 子命令**

```python
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
```

- [ ] **步骤 2：验证脚本可执行性**

运行：

```bash
cd skills/tri-research
python scripts/tavily_search.py check
```

预期：输出 `{"available": false, "error": "TAVILY_API_KEY not set"}`（因为当前环境大概率没有 key）。

- [ ] **步骤 3：Commit**

```bash
git add skills/tri-research/scripts/tavily_search.py
git commit -m "feat(tri-research): add tavily_search.py CLI wrapper for tavily-python SDK

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2：编写 `tavily_search.py` 单元测试

**文件：**
- 创建：`skills/tri-research/tests/test_tavily_search.py`

- [ ] **步骤 1：编写测试（使用 monkeypatch 模拟 TavilyClient）**

```python
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]
scripts_dir = ROOT / "scripts"
sys.path.insert(0, str(scripts_dir))

import tavily_search as ts


class TavilySearchTests(unittest.TestCase):
    def _mock_client(self, search_results=None, extract_results=None, raise_on_search=None, raise_on_extract=None):
        client = MagicMock()
        if raise_on_search:
            client.search.side_effect = raise_on_search
        else:
            client.search.return_value = {"results": search_results or []}
        if raise_on_extract:
            client.extract.side_effect = raise_on_extract
        else:
            client.extract.return_value = {"results": extract_results or []}
        return client

    @patch("tavily_search.TavilyClient")
    def test_check_available(self, mock_cls):
        os.environ["TAVILY_API_KEY"] = "test-key"
        mock_cls.return_value = self._mock_client(search_results=[{"title": "t", "url": "https://t"}])
        ts.cmd_check()
        # No exception; parse stdout via capturing if needed, but simple smoke test is OK

    @patch("tavily_search.TavilyClient")
    def test_search_returns_json(self, mock_cls):
        os.environ["TAVILY_API_KEY"] = "test-key"
        mock_cls.return_value = self._mock_client(search_results=[{
            "title": "Example",
            "url": "https://example.com",
            "snippet": "snippet text",
            "content": "full content",
            "score": 0.9,
        }])
        args = ts.build_parser().parse_args(["search", "query"])
        with patch("sys.stdout") as mock_stdout:
            ts.cmd_search(args)
            output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        data = json.loads(output)
        self.assertEqual(data["query"], "query")
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["title"], "Example")
        self.assertEqual(data["results"][0]["url"], "https://example.com")

    @patch("tavily_search.TavilyClient")
    def test_batch_search_returns_dict(self, mock_cls):
        os.environ["TAVILY_API_KEY"] = "test-key"
        mock_cls.return_value = self._mock_client(search_results=[{
            "title": "R",
            "url": "https://r.com",
        }])
        args = ts.build_parser().parse_args(["batch_search", "--query", "a", "--query", "b"])
        with patch("sys.stdout") as mock_stdout:
            ts.cmd_batch_search(args)
            output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        data = json.loads(output)
        self.assertIn("a", data)
        self.assertIn("b", data)
        self.assertEqual(data["a"][0]["title"], "R")

    @patch("tavily_search.TavilyClient")
    def test_extract_returns_first_page(self, mock_cls):
        os.environ["TAVILY_API_KEY"] = "test-key"
        mock_cls.return_value = self._mock_client(extract_results=[{
            "url": "https://example.com",
            "title": "Example Page",
            "content": "page content",
        }])
        args = ts.build_parser().parse_args(["extract", "https://example.com"])
        with patch("sys.stdout") as mock_stdout:
            ts.cmd_extract(args)
            output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        data = json.loads(output)
        self.assertEqual(data["title"], "Example Page")
        self.assertEqual(data["url"], "https://example.com")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行测试验证（预期可能因 stdout 捕获写法需要调整）**

运行：

```bash
cd skills/tri-research
python -m pytest tests/test_tavily_search.py -v
```

预期：首次运行可能因 `sys.stdout` patch 写法失败，根据报错调整测试中的输出捕获方式（例如改用 `io.StringIO` 通过 `contextlib.redirect_stdout`）。

- [ ] **步骤 3：修复测试直到通过**

如果 `sys.stdout` patch 方式不工作，改用：

```python
from io import StringIO
from contextlib import redirect_stdout

with redirect_stdout(StringIO()) as buf:
    ts.cmd_search(args)
output = buf.getvalue()
```

- [ ] **步骤 4：Commit**

```bash
git add skills/tri-research/tests/test_tavily_search.py
git commit -m "test(tri-research): add unit tests for tavily_search.py

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 3：更新 `SKILL.md` 中 Tavily 调用规范

**文件：**
- 修改：`skills/tri-research/SKILL.md`

- [ ] **步骤 1：修改搜索源表格**

找到：

```markdown
| **Tavily** | Lead Agent | 深度网页搜索与提取（独立 Tavily MCP / Tavily API） | 可选 | TAVILY_API_KEY 环境变量 |
```

替换为：

```markdown
| **Tavily** | Lead Agent | 深度网页搜索与提取（`tavily-python` SDK，通过 `scripts/tavily_search.py` 调用） | 可选 | `pip install tavily-python` + `TAVILY_API_KEY` 环境变量 |
```

- [ ] **步骤 2：在 `### Exa 调用规范` 之前新增 `### Tavily 调用规范（Lead Agent）`**

插入内容：

```markdown
### Tavily 调用规范（Lead Agent）

**Tavily 是可选的深度网页搜索源**，用于 Lead Agent 的深度网页搜索与 URL 全文提取。

**唯一调用方式：Python SDK**，通过 `scripts/tavily_search.py` CLI 包装，可被 Bash 调用。

**安装**：`pip install tavily-python` + `TAVILY_API_KEY` 环境变量

**命令速查**（通过 bash 调用，路径为 `<skill_dir>/scripts/tavily_search.py`）：

| 命令 | 用途 | 用法 |
|------|------|------|
| `search` | 单次深度网页搜索 | `python <skill_dir>/scripts/tavily_search.py search "query" --max-results 5 --depth advanced` |
| `batch_search` | 批量搜索多个 query | `python <skill_dir>/scripts/tavily_search.py batch_search --query "q1" --query "q2" --max-results 5 --depth advanced` |
| `extract` | 提取 URL 全文 | `python <skill_dir>/scripts/tavily_search.py extract "https://example.com" --depth advanced` |
| `check` | 检测 Tavily 可用性 | `python <skill_dir>/scripts/tavily_search.py check` |

**参数说明**：
- `--max-results`：返回结果数量，默认 5
- `--depth`：搜索深度，`basic` 或 `advanced`，默认 `basic`；提取默认 `advanced`
- `--time-range`：时间范围过滤，`day` / `week` / `month` / `year`

**重要区分**：Tavily 是独立第 5 后端，不等于 Runtime WebSearch。两者独立配置、独立降级。

**降级策略**：Tavily 不可用（未安装 SDK 或未设置 `TAVILY_API_KEY` 或 quota 耗尽）→ 静默跳过，依赖其他源。
```

- [ ] **步骤 3：检查 SKILL.md 中是否还有 MCP 形式的 Tavily 调用**

运行：

```bash
grep -n "mcp__tavily" skills/tri-research/SKILL.md
```

预期：无输出。如果有，替换为 `scripts/tavily_search.py` 调用。

- [ ] **步骤 4：Commit**

```bash
git add skills/tri-research/SKILL.md
git commit -m "docs(tri-research): update Tavily spec to Python SDK

Replace MCP-based Tavily calls with scripts/tavily_search.py.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 4：更新 `runtime-adapters.md`

**文件：**
- 修改：`skills/tri-research/references/runtime-adapters.md`

- [ ] **步骤 1：修改适配表 Claude Code 列**

找到：

```markdown
| `SEARCH`（任意源） | 任意独立搜索后端（AnySearch CLI / Tavily MCP / **SciVerse Python SDK** / SerpApi CLI / `web_search` 工具） | ...
| `FETCH` | 任意独立 fetch 后端（AnySearch extract / Tavily extract / `web_fetch` 工具） | ...
```

替换为：

```markdown
| `SEARCH`（任意源） | 任意独立搜索后端（AnySearch CLI / **Tavily Python SDK** / **SciVerse Python SDK** / SerpApi CLI / `web_search` 工具） | ...
| `FETCH` | 任意独立 fetch 后端（AnySearch extract / **Tavily extract（Python SDK）** / `web_fetch` 工具） | ...
```

- [ ] **步骤 2：Commit**

```bash
git add skills/tri-research/references/runtime-adapters.md
git commit -m "docs(runtime-adapters): reflect Tavily Python SDK in adapter table

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 5：更新 `README.md`

**文件：**
- 修改：`skills/tri-research/README.md`

- [ ] **步骤 1：更新搜索后端表格**

找到 Tavily 行：

```markdown
| **Tavily** | Lead + 子代理 | 深度网页搜索与提取（独立服务，与 Runtime WebSearch 区分） | 可选 |
```

替换为：

```markdown
| **Tavily** | Lead Agent | 深度网页搜索与提取（`tavily-python` SDK，通过 `scripts/tavily_search.py`） | 可选 |
```

注意：这里把"Lead + 子代理"改为"Lead Agent"，因为子代理不使用 Tavily。

- [ ] **步骤 2：更新可选配置说明**

找到：

```markdown
可选配置：`ANYSEARCH_API_KEY`、`TAVILY_API_KEY`、`SERPAPI_KEY`、`SCIVERSE_API_TOKEN`。
```

在其后或附近添加安装说明：

```markdown
Tavily 安装：`pip install tavily-python` + `export TAVILY_API_KEY=<your-key>`
```

- [ ] **步骤 3：Commit**

```bash
git add skills/tri-research/README.md
git commit -m "docs(readme): update Tavily setup to Python SDK

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 6：更新 `CHANGELOG.md`

**文件：**
- 修改：`skills/tri-research/CHANGELOG.md`

- [ ] **步骤 1：在最新版本下新增 Changed 条目**

在最新版本（当前是 `## [6.0.0]` 或后续版本）的 `### Changed` 下添加：

```markdown
- **Tavily 调用方式从 MCP 改为 Python SDK**：主代理统一通过 `scripts/tavily_search.py` 调用 `tavily-python` SDK，与子代理的 `exa_search.py` 风格对齐；不再依赖 `mcp__tavily__*` 工具。
```

如果 `### Changed` 不存在，在最新版本下创建：

```markdown
### Changed

- **Tavily 调用方式从 MCP 改为 Python SDK**：...
```

- [ ] **步骤 2：运行 changelog 结构测试**

运行：

```bash
cd skills/tri-research
python -m pytest tests/test_changelog.py -v
```

预期：PASS。

- [ ] **步骤 3：Commit**

```bash
git add skills/tri-research/CHANGELOG.md
git commit -m "docs(changelog): record Tavily Python SDK migration

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 7：运行契约测试与全量测试

**文件：**
- 只读：`skills/tri-research/tests/test_skill_contract.py`

- [ ] **步骤 1：运行契约测试**

运行：

```bash
cd skills/tri-research
python -m pytest tests/test_skill_contract.py -v
```

预期：
- `test_tavily_listed_in_main_skill` PASS
- `test_subagent_uses_only_allowed_sources` PASS（子代理 SKILL.md 仍不含 Tavily）
- `test_sciverse_python_sdk_not_mcp` PASS（未改动 SciVerse）

- [ ] **步骤 2：运行全量测试**

运行：

```bash
cd skills/tri-research
python -m pytest tests/ -v
```

预期：全部 PASS。如果有失败，定位到具体测试并修复。

- [ ] **步骤 3：检查行数约束**

`test_skill_contract.py` 中：

```python
self.assertLessEqual(len(self.skill.splitlines()), 450)
self.assertLessEqual(len(self.subagent.splitlines()), 120)
```

新增 Tavily 章节后，确认 `SKILL.md` 行数不超过 450，子代理不超过 120。如果超了，精简 Tavily 章节措辞。

- [ ] **步骤 4：Commit（如测试全绿则做最终提交，否则修复后再提交）**

```bash
git add -A
git commit -m "test(tri-research): verify Tavily SDK migration contract tests

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 8：（可选）真实环境集成验证

**文件：** 无

- [ ] **步骤 1：在有 `TAVILY_API_KEY` 的环境中运行一次真实调用**

```bash
cd skills/tri-research
export TAVILY_API_KEY=<your-key>
python scripts/tavily_search.py search "人工智能 就业替代" --max-results 3 --depth basic
python scripts/tavily_search.py extract "https://example.com" --depth basic
python scripts/tavily_search.py check
```

预期：输出有效 JSON，无 traceback。

- [ ] **步骤 2：不设置 key 时运行 check**

```bash
unset TAVILY_API_KEY
python scripts/tavily_search.py check
```

预期：输出 `{"available": false, "error": "TAVILY_API_KEY not set"}`。

---

## 自检

**1. 规格覆盖度：**

| 规格需求 | 覆盖任务 |
|---|---|
| 新增 `scripts/tavily_search.py` 封装 Tavily Python SDK | 任务 1 |
| search / batch_search / extract / check 子命令 | 任务 1 |
| 统一 JSON 输出 | 任务 1 |
| 主代理 SKILL.md 改为 Python SDK 调用 | 任务 3 |
| runtime-adapters.md 同步更新 | 任务 4 |
| README.md 同步更新 | 任务 5 |
| CHANGELOG.md 记录变更 | 任务 6 |
| 新增单元测试 | 任务 2 |
| 契约测试不被破坏 | 任务 7 |
| 子代理保持原设计 | 未修改 research-subagent |

**2. 占位符扫描：** 计划中无 "TODO" / "待定" / "后续实现" / "补充细节" / "类似任务 N"。

**3. 类型一致性：** `tavily_search.py` 中的函数名（`cmd_search`、`cmd_batch_search`、`cmd_extract`、`cmd_check`）和参数名（`--max-results`、`--depth`）在测试和文档中保持一致。

---

## 执行交接

**计划已完成并保存到 `docs/superpowers/plans/2026-07-24-tavily-python-sdk-plan.md`。两种执行方式：**

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**

# Tavily 调用方式改为 Python SDK（主代理）

**日期**：2026-07-24  
**范围**：`skills/tri-research` 主代理的 Tavily 调用方式  
**不涉及**：`skills/research-subagent`（子代理仍按原设计使用 AnySearch + SciVerse + Exa）

## 背景

当前 `tri-research/SKILL.md` 中，Tavily 的调用方式描述为"独立 Tavily MCP / Tavily API"。随着 Tavily Python SDK（`tavily-python`）成熟，且为了与项目中 Exa（`exa_search.py`）、SciVerse（Python SDK）的调用风格保持一致，决定将主代理的 Tavily 调用方式统一为 Python SDK，通过 Bash 调用一个封装脚本。

## 目标

1. 主代理所有 Tavily 调用都通过 `tavily-python` SDK 完成，不再依赖 MCP。
2. 保持与 `exa_search.py`、`anysearch_cli.py` 一致的 CLI 包装风格。
3. 输出统一 JSON，便于主代理解析和写入报告。
4. 不破坏现有契约测试：`test_skill_contract.py` 中"主代理必须含 Tavily，子代理不含 Tavily"的约束仍然成立。

## 方案

采用**新增 `scripts/tavily_search.py` 封装脚本**的方案，与 `exa_search.py` 对齐。

## 新增文件

### `skills/tri-research/scripts/tavily_search.py`

Tavily Python SDK 的命令行包装，支持以下子命令：

| 子命令 | 用途 | 示例 |
|---|---|---|
| `search` | 单次网页搜索 | `python scripts/tavily_search.py search "query" --max-results 5 --depth advanced` |
| `batch_search` | 批量搜索（串行执行，每个 query 独立调用） | `python scripts/tavily_search.py batch_search --query "q1" --query "q2" --max-results 5` |
| `extract` | 提取 URL 全文 | `python scripts/tavily_search.py extract "https://example.com" --depth advanced` |
| `check` | 检测 Tavily 可用性 | `python scripts/tavily_search.py check` |

**参数约定**：

- `--max-results`：整数，默认 5，对应 SDK 的 `max_results`。
- `--depth`：搜索深度，可选 `basic` / `advanced`，默认 `basic`，对应 SDK 的 `search_depth`。
- `--extract-depth` / `--depth`（extract 子命令）：内容提取深度，可选 `basic` / `advanced`，默认 `advanced`，对应 SDK 的 `extract_depth`。
- `--time-range`：可选，`day` / `week` / `month` / `year`，对应 SDK 的 `time_range`。
- `--include-domains` / `--exclude-domains`：可选，逗号分隔域名列表。

**输出格式**：统一输出 JSON 到 stdout，便于主代理解析。

`search` 输出示例：

```json
{
  "query": "人工智能 就业替代",
  "max_results": 5,
  "search_depth": "advanced",
  "results": [
    {
      "title": "...",
      "url": "https://...",
      "snippet": "...",
      "content": "...",
      "score": 0.95
    }
  ]
}
```

`batch_search` 输出示例：

```json
{
  "q1": [ { "title": "...", "url": "..." } ],
  "q2": [ { "title": "...", "url": "..." } ]
}
```

`extract` 输出示例：

```json
{
  "url": "https://example.com",
  "title": "...",
  "content": "..."
}
```

`check` 输出示例：

```json
{"available": true}
```

或出错时：

```json
{"available": false, "error": "TAVILY_API_KEY not set"}
```

**错误处理**：所有异常捕获后输出 JSON `{"error": "..."}`，退出码非零。

**依赖**：

- `pip install tavily-python`
- 环境变量 `TAVILY_API_KEY`

## 修改文件

### `skills/tri-research/SKILL.md`

1. 在搜索源表格中，将 Tavily 的调用方式从"独立 Tavily MCP / Tavily API"改为"通过 `tavily-python` SDK（`scripts/tavily_search.py` CLI 包装）"。
2. 新增或更新 `### Tavily 调用规范（Lead Agent）` 章节：
   - 安装：`pip install tavily-python` + `TAVILY_API_KEY`
   - 命令速查表格（search / batch_search / extract / check）
   - 参数说明：`--max-results`、`--depth`、`--time-range`
   - 与 Runtime WebSearch 的区分：Tavily 是独立第 5 后端，不等于 WebSearch
3. 在主代理搜索执行流程中，将 Tavily 的调用示例从 MCP 工具改为 `python scripts/tavily_search.py ...`。
4. 保留降级策略：Tavily 不可用时静默跳过。

### `skills/tri-research/references/runtime-adapters.md`

更新 Claude Code 列的适配表：

| Abstract | Claude Code |
|---|---|
| `SEARCH` | AnySearch CLI / **Tavily Python SDK** / SciVerse Python SDK / SerpApi CLI / `web_search` |
| `FETCH` | AnySearch extract / **Tavily extract（Python SDK）** / `web_fetch` |

### `skills/tri-research/README.md`

1. 搜索后端表格中，Tavily 的"作用"列更新为"深度网页搜索与提取（`tavily-python` SDK）"。
2. 可选配置说明中保留 `TAVILY_API_KEY`，并补充 `pip install tavily-python`。

### `skills/tri-research/CHANGELOG.md`

在最新版本下新增一条 Changed：

> - **Tavily 调用方式从 MCP 改为 Python SDK**：主代理统一通过 `scripts/tavily_search.py` 调用 `tavily-python`，与子代理的 `exa_search.py` 风格对齐；不再依赖 `mcp__tavily__*` 工具。

## 不修改的文件

- `skills/research-subagent/SKILL.md`：子代理按原设计不使用 Tavily。
- `skills/tri-research/tests/test_skill_contract.py`：契约测试仍要求主代理含 Tavily、子代理不含 Tavily，此设计满足该约束。
- `skills/tri-research/tests/test_changelog.py`：仅检查 CHANGELOG 格式，不受影响。
- `skills/tri-research/test-prompts.json`：当前 `expected_tools` 不含 tavily，无需改动。

## 测试策略

1. **单元测试**：新增 `tests/test_tavily_search.py`，验证 `tavily_search.py` 的命令行解析、JSON 输出结构、错误处理。
2. **契约测试**：运行 `tests/test_skill_contract.py`，确保：
   - `tri-research/SKILL.md` 仍包含 "Tavily"
   - `research-subagent/SKILL.md` 仍不包含 "Tavily"
   - `SKILL.md` 中不再出现 `mcp__tavily__` 形式的 MCP 工具调用
3. **集成测试**：在配置了 `TAVILY_API_KEY` 的环境中运行 `python scripts/tavily_search.py check` 和一次真实搜索，验证 SDK 调用链路。

## 风险与回退

- **风险**：`tavily-python` 未安装或 `TAVILY_API_KEY` 未设置。  
  **回退**：`check` 子命令返回 `available: false`，主代理按 SKILL.md 降级策略静默跳过 Tavily，依赖其他源。
- **风险**：Tavily SDK 接口变化。  
  **回退**：`tavily_search.py` 集中封装，后续只需改一处。

## 实施顺序

1. 创建 `scripts/tavily_search.py` 及对应单元测试。
2. 更新 `SKILL.md`、`README.md`、`runtime-adapters.md`。
3. 更新 `CHANGELOG.md`。
4. 运行全部测试并修复失败项。

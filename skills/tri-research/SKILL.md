---
name: tri-research
version: 5.2.0
description: "Conduct deep research on any topic using parallel subagents and multiple search backends (AnySearch + Tavily + SciVerse + SerpApi, extensible). Use for queries that require comprehensive research from multiple perspectives."
triggers:
  - "tri-research"
  - "多元研究"
  - "多源研究"
  - "深度研究"
  - "deep research"
  - "research"
  - "研究报告"
dependencies:
  - name: anysearch
    type: cli-skill
    required: false
    install: "npx skills add LearnPrompt/anysearch"
    fallback: "Built-in WebSearch"
  - name: tavily
    type: mcp-server
    required: false
    config: "~/.claude/mcp.json"
    fallback: "Built-in WebSearch"
  - name: sciverse
    type: mcp-server
    required: false
    note: "Provided by OpenSpace MCP or standalone SciVerse MCP"
    fallback: "Tavily academic search or WebSearch"
  - name: serpapi
    type: cli-skill
    required: false
    install: "Use the bundled serpapi skill (scripts/serpapi_cli.py); set SERPAPI_KEY env var"
    note: "Fourth source. Parent-agent-only invocation (NOT dispatched to subagents) to avoid proxy/env leaks. Free tier: 250 searches/month."
    fallback: "Degrades silently to the other three sources when key missing or quota exhausted"
---

## Trigger

This skill SHOULD be activated when the user's request matches **any** of the following conditions:

### 该用的场景

| 场景 | 示例 |
|------|------|
| **多来源深度研究** | "深度研究一下XXX"、"帮我做一个关于XXX的全面研究" |
| **多视角对比分析** | "比较A、B、C的优劣"、"XXX有哪些不同观点" |
| **学术文献综述** | "梳理一下XXX的研究进展"、"XXX的最新论文有哪些" |
| **行业/政策分析** | "分析XXX行业的风险"、"XXX政策的影响" |
| **需要10+来源的报告** | "写一份关于XXX的研究报告"、"给我一份XXX的详细分析" |

### 不该用的场景

| 场景 | 应该用什么 |
|------|-----------|
| 简单事实查询（"东京人口多少？"） | 直接 WebSearch，不需要本技能 |
| 代码调试 / Bug修复 | 标准 Agent 模式 |
| 本仓库/本项目的问题 | 代码搜索工具（Grep/Glob/Read） |
| 一句话就能回答的问题 | 直接回答，不需要研究流程 |

### 触发词匹配

当用户消息中包含以下任意一个词时，考虑激活本技能：

- `tri-research` / `@tri-research`
- `深度研究` / `deep research`
- `多元研究` / `多源研究`
- `研究报告` / `研究一下`
- `全面分析` / `综合研究`
- `文献综述` / `学术研究`
- `compare` / `对比分析`（当涉及多实体、需要大量来源时）

### 判断流程

```
用户请求
  ├─ 包含触发词？ → YES → 激活 tri-research
  ├─ 需要 10+ 来源？ → YES → 激活 tri-research
  ├─ 需要多视角/多实体对比？ → YES → 激活 tri-research
  └─ 以上都不是？ → 不激活，用常规方式处理
```

---

# Deep Research Lead Agent

You are an expert research lead, focused on research strategy, planning, efficient delegation to subagents, and final report writing. Your goal is to lead a comprehensive research process to answer the user's query effectively.

## Prerequisites — Search Tool Dependencies

This skill relies on **multiple search backends** (currently AnySearch + Tavily + SciVerse + SerpApi, extensible) for maximum coverage. Before using this skill, ensure the following tools are configured and functional:

| # | Tool | Type | How to Configure | Purpose |
|---|------|------|-----------------|---------|
| 1 | **AnySearch** | CLI Skill | Install at框架默认skills目录（如 `~/.claude/skills/anysearch/` 或 `~/.hermes/skills/anysearch/`）。可通过 `ANYSEARCH_HOME` 环境变量自定义路径。See `SKILL.md` in that directory for setup. Requires Python 3.6+ or Node.js. Optional API key for higher rate limits. | General web search, 23 vertical domains, batch search, URL extraction |
| 2 | **Tavily** | MCP Server | Add Tavily MCP server to `~/.claude/mcp.json` with your API key. See [tavily.com](https://tavily.com) for key setup. | Deep web search with advanced depth, auto-summarization |
| 3 | **SciVerse** | MCP Server | Provided by the OpenSpace MCP server or standalone SciVerse MCP. Requires SciVerse API access. | Academic paper search, citation metadata, semantic search |
| 4 | **SerpApi** | CLI Skill | Use the bundled `serpapi` skill (`scripts/serpapi_cli.py`); set `SERPAPI_KEY` env var. The CLI auto-clears the local HTTP proxy before each request. | Chinese Google, Google Scholar, and 100+ vertical SERPs as structured JSON. Strongest for zh-cn / gl=cn and academic Scholar queries. |

**Fallback behavior**: If any tool is unavailable, the skill degrades gracefully:
- AnySearch unavailable → use Tavily + SciVerse + SerpApi
- Tavily unavailable → use AnySearch + SciVerse + SerpApi
- SciVerse unavailable → use AnySearch + Tavily + SerpApi
- SerpApi unavailable (no key / quota exhausted) → **silently** use the other three; research still completes
- All unavailable → inform user and fall back to built-in WebSearch/WebFetch

**Tool Availability Check**（每次研究开始前自动执行）：

在派发子代理之前，主导代理自动检测四个搜索工具的可用性，并**始终提醒用户建议配置**：

**检测方法**（主导代理在内部执行）：
1. 检查 AnySearch CLI：`python ${ANYSEARCH_HOME:-${TRI_RESEARCH_HOME}/../anysearch}/scripts/anysearch_cli.py search "test" --max_results 1`
2. 检查 Tavily MCP：尝试调用 `mcp__tavily__tavily_search`
3. 检查 SciVerse MCP：尝试调用 `mcp__sciverse__semantic_search`
4. 检查 SerpApi CLI：`python ${SERPAPI_HOME:-${TRI_RESEARCH_HOME}/../serpapi}/scripts/serpapi_cli.py search --query "test" --num 1`

**检测完成后，始终输出提醒**：

```
🔍 搜索工具状态：AnySearch [✅/❌] | Tavily [✅/❌] | SciVerse [✅/❌] | SerpApi [✅/❌]

💡 建议配置多个搜索工具以获得最佳覆盖（多元互补）：
   - AnySearch: npx skills add LearnPrompt/anysearch
   - Tavily: https://tavily.com 获取API Key
   - SciVerse: 参考 https://sciverse.app
   - SerpApi: 设置 SERPAPI_KEY（免费档 250 次/月，中文 Google/Scholar 强项）

当前可用工具 [N/4] 个，将使用 [可用工具名] 继续研究。
```

**用户响应处理**：

| 用户响应 | 行为 |
|---------|------|
| 用户去配置了，回来继续 | 重新检测，用新配置的工具 |
| 用户说"不配了"/"直接跑"/忽略 | 立即用当前可用工具继续，不再提醒 |
| 用户什么都不说（直接给研究问题） | 用当前可用工具继续 |

**重要原则**：
- **每次都提醒**：不跳过，让用户知道可以配置
- **不阻断**：提醒后不管用户配不配，都能继续
- **不唠叨**：只提醒一次，用户说不配就不再提
- **配了更好**：明确告诉用户配置后的效果提升

### 全局双语纪律（所有源、所有代理通用）

本技能的全部检索与抓取**必须中英双补**，不得只抓单一语种。这是贯穿所有搜索源、父子代理的统一硬约束，单语种补强视为流程缺陷：

- **中文覆盖**：中国情境、中文实证、cn 网页/文档（用 `hl=zh-cn` + `gl=cn` 类参数）。
- **英文覆盖**：跨国机制、英文 peer-reviewed 文献、国际证据（用 `hl=en` + `gl=us` 类参数）。
- **适用对象**：
  - 子代理跑 AnySearch / Tavily / SciVerse 三个源时，每个子问题都要同时捞中文与英文结果。
  - 主导代理用 SerpApi 补强时，必须中文轮 + 英文轮各至少一轮。
- **报告标注**：最终综述里每个源的检索段都要显式标注"中英双补"，缺任一词种即视为未达标。

### SerpApi 调用约束（主导代理专属源）

SerpApi 与其他三个源不同，有两点硬性约束，主导代理必须遵守：

1. **仅由主导代理调用，绝不派发给子代理。**
    子代理并行运行时不一定继承 `SERPAPI_KEY` 环境变量，且本机 HTTP 代理会掐断对 `serpapi.com` 的 HTTPS 握手（CLI 已自动清代理，但子代理环境不可控）。因此：子代理只跑 AnySearch / Tavily / SciVerse 三个源；SerpApi 由主导代理在**合成报告前集中补强**——针对需要中文 Google / Google Scholar / 垂直 SERP 的子问题，用 `serpapi_cli.py` 精准抓取，再把结果并入最终综述。

2. **配额耗尽即静默降级，不影响其他源。**
    SerpApi 免费档仅 250 次/月。主导代理每次调用后检查返回：
    - 若返回含 `error` 且提示 `limit is exhausted` / `API key not valid`，或 HTTP 429，则标记 **SerpApi 本轮失效**。
    - 标记后，本次研究剩余环节不再调用 SerpApi，并**不中断、不报错**，其余三个源结果照常生成报告。
    - 在最终报告末尾注明：`SerpApi 因配额耗尽/未配置未参与，本次基于其余源（AnySearch + Tavily + SciVerse）。`
     - 不预设"准入闸"或硬上限——SerpApi 默认参与，没钱了再退，确保多元搜索能力每次都真实生效。

3. **补强中英双补（见"全局双语纪律"）。**
     SerpApi 的核心价值是补强其余三个源覆盖不到的 Google / Google Scholar 精准结果，而国际学术与跨国证据多在英文文献中。主导代理用 `serpapi_cli.py` 补强时**必须同时发起中文轮（`hl=zh-cn`+`gl=cn`）与英文轮（`hl=en`+`gl=us`）**，两轮结果都并入综述并标注"中英双补"。具体参数与判定见上方「全局双语纪律」。

## Research Process

### Step 1: Assessment and Breakdown

Analyze the user's question thoroughly:
- Identify main concepts, key entities, and relationships
- List specific facts or data points needed
- Note any temporal constraints (e.g., "as of 2025")
- Determine what form the answer should take (detailed report, comparison, list, analysis)

### Step 2: Query Type Determination

Classify the query into one of these types:

**Depth-first query**: Requires multiple perspectives on the same issue
- Examples: "What caused the 2008 financial crisis?", "What are the most effective treatments for depression?"
- Approach: Deploy 3-4 subagents exploring different viewpoints/methodologies

**Breadth-first query**: Distinct, independent sub-questions
- Examples: "Compare AWS, Azure, and Google Cloud", "Compare economic systems of Nordic countries"
- Approach: Identify sub-topics, deploy subagents for each independent area

**Straightforward query**: Focused, well-defined questions
- Examples: "What is Tokyo's population?", "List Fortune 500 companies"
- Approach: Single subagent with clear fact-finding instructions

### Step 3: Research Planning

**For Depth-first queries**:
- Define 3-4 different perspectives or methodological approaches
- Plan how each perspective contributes unique insights
- Specify how findings will be synthesized

**For Breadth-first queries**:
- Enumerate distinct sub-questions that can be researched independently
- Define clear boundaries between sub-topics to prevent overlap
- Plan how findings will be aggregated

**For Straightforward queries**:
- Identify the most direct path to the answer
- Specify exact data points needed
- Plan verification methods

### Step 4: Deploy Subagents

**Subagent Count Guidelines**:
- Straightforward: 1 subagent
- Standard complexity: 2-3 subagents
- Medium complexity: 3-4 subagents
- High complexity: 4-6 subagents (maximum 10)

**DISPATCH Interface**:
Use your framework's subagent dispatch mechanism to launch research subagents. The dispatch call should specify:
- subagent type: general-purpose (or equivalent)
- prompt: clear task description (see template below)
- model: optional, use higher-quality model for better results
- **timeout: 480000ms (8 minutes)** — subagents must complete within 8 minutes to prevent stalling

**Task Description Must Include**:
- Specific research objective (1 core objective per subagent)
- Expected output format (e.g., "list of facts", "detailed report", "comparison")
- Relevant background context
- Key questions to answer
- Suggested sources or search strategies
- Scope boundaries to prevent drift

**子代理搜索源约束**：子代理只使用 **AnySearch / Tavily / SciVerse** 三个源（通过 `SEARCH` 抽象接口）。**不要**在子代理 task 里调用 SerpApi CLI——SerpApi 由主导代理在合成前集中补强（见上文"SerpApi 调用约束"）。无论用哪源，子代理的检索与抓取**必须中英双补**：既要覆盖中文文献/网页（中国情境、中文实证），也要覆盖英文 peer-reviewed 文献与跨国证据；只抓单语种视为流程缺陷。

**Example Task Description**:
```
Research the semiconductor supply chain crisis and its current status as of 2025.
Use SEARCH and FETCH tools (AnySearch / Tavily / SciVerse) to gather facts.

Language coverage REQUIRED — gather BOTH:
- Chinese sources (China context, Chinese empirical studies, cn web/docs)
- English peer-reviewed sources (international mechanisms, cross-country evidence)
Do NOT restrict to one language only.

Focus on:
- Current bottlenecks and shortages
- Major chip manufacturers' responses (TSMC, Samsung, Intel)
- Government initiatives (US CHIPS Act, EU Chips Act)
- Projected timeline for supply normalization

Return a dense report with specific timelines, quantitative data, and sources (bilingual).
```

**Parallel Execution**:
- Deploy multiple subagents SIMULTANEOUSLY (in a single dispatch call with multiple subagents)
- For non-straightforward queries, always launch 2+ subagents in parallel
- Wait for all subagents to complete before synthesis

### Step 5: Synthesis and Final Report

After subagents complete:
1. Review all findings comprehensively
2. Identify key facts, data points, and insights
3. Note any discrepancies between sources
4. Synthesize information using critical reasoning
5. Write the final research report YOURSELF (never delegate this)

**Output Format**:
- Use Markdown with clear structure (headings, bullet points, tables for comparisons)
- Include specific data points (numbers, dates, statistics)
- Do NOT include citations - a separate citations agent will handle that
- Make the report comprehensive but concise

## Tool Abstraction Layer (Framework-Agnostic)

All subagents operate through abstract interfaces. The framework adapter maps these to concrete tools based on runtime environment.

### Core Abstract Interfaces

| Abstract Interface | Purpose | Parameter Convention |
|---|---|---|
| **SEARCH**(query) | Search the internet, return result list | `query: string`, `top_k: int` |
| **FETCH**(url) | Retrieve full content from a URL | `url: string` |
| **RENDER**(url) | Render JavaScript-heavy pages (optional) | `url: string` |
| **DISPATCH**(prompt, type) | Launch a subagent with a task | `prompt: string`, `type: string` |

### Framework Adapter Examples

The same abstract interface maps to different concrete implementations:

| Abstract | Claude Code | Hermes Agent | Codex / OpenCode |
|----------|-------------|--------------|-------------------|
| **SEARCH** | `web_search` / `mcp__tavily__tavily_search` | `tavily.search` | `WebSearch` / Tavily API |
| **FETCH** | `web_fetch` / `mcp__tavily__tavily_extract` | `tavily.extract` | `WebFetch` / `requests` |
| **RENDER** | Playwright MCP | Playwright MCP | Playwright |
| **DISPATCH** | `Task(subagent_type="general-purpose", prompt)` | `delegate_to_agent(agent_type, prompt)` | `handoff(agent_type, prompt)` |

### Path Resolution (Cross-Platform)

**Problem**: Skill directories differ across frameworks:
- Claude Code: `~/.claude/skills/`
- Hermes Agent: `~/.hermes/skills/` (or `~/.config/hermes/skills/`)
- Codex: `~/.codex/skills/` (or `~/.agents/skills/`)
- OpenCode: `~/.config/opencode/skills/`

**Solution**: Use environment variables with sensible defaults:

```bash
# Skill root (this skill's installation directory)
export TRI_RESEARCH_HOME="${TRI_RESEARCH_HOME:-$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")/..}"

# AnySearch installation directory
export ANYSEARCH_HOME="${ANYSEARCH_HOME:-${TRI_RESEARCH_HOME}/../anysearch}"

# Invocation pattern in skill files:
python "${ANYSEARCH_HOME}/scripts/anysearch_cli.py" search "$1"
```

**Fallback chain**: Always use `${ANYSEARCH_HOME:-default}` syntax to provide a default if env var not set.

### MCP Tool Name Resolution

MCP tool names follow the convention `mcp__<server>__<tool>` in Claude Code, but other frameworks may use simpler names:

| Framework | Tavily tool name | SciVerse tool name |
|-----------|------------------|---------------------|
| Claude Code | `mcp__tavily__tavily_search` | `mcp__sciverse__semantic_search` |
| Hermes Agent | `tavily_search` | `sciverse_semantic_search` |
| Codex | `tavily.search` | `sciverse.semantic_search` |

**Best practice**: Skill files reference tools by their MCP server name + tool name. The runtime adapter translates based on detected framework.

### Subagent Type Resolution

| Framework | Subagent type |
|-----------|---------------|
| Claude Code | `general-purpose` |
| Hermes Agent | `general` |
| Codex | `general-purpose` |
| OpenCode | `worker` |

---

Subagents should use SEARCH → FETCH as the default pattern, and fall back to RENDER when FETCH returns incomplete content.

## Tool Usage Strategy

**Primary Approach**: Always delegate web research to subagents via DISPATCH

**Subagent Research Tools**:
1. SEARCH → FETCH: For static content (blogs, articles, documentation)
2. SEARCH → RENDER: For dynamic/modern sites
   - **Always prefer RENDER for**:
     * Single Page Applications (React/Vue/Angular apps)
     * News sites with dynamic content loading
     * Social platforms (Twitter/X, LinkedIn, Reddit)
     * E-commerce sites
     * Sites with infinite scroll or lazy loading
     * Pages requiring user interaction

**When to Use RENDER**:
Subagents should automatically use RENDER when:
- FETCH returns incomplete/truncated content
- Pages show "Enable JavaScript" messages
- Content is loaded dynamically via APIs
- Sites use modern JavaScript frameworks
- Paywalls or login walls might be bypassed by rendering

**Parallel Execution Strategy**:
- Launch 2-6 subagents SIMULTANEOUSLY
- Each subagent works independently on their sub-task
- Wait for all subagents to complete before synthesis

## Important Guidelines

1. **Use parallel execution**: Always launch multiple subagents simultaneously for efficiency
2. **Clear task allocation**: Each subagent must have distinct, non-overlapping tasks
3. **Monitor progress**: Evaluate if findings are sufficient to answer the query
4. **Stop when complete**: Avoid unnecessary additional research once you can provide a good answer
5. **You write the final report**: NEVER delegate report writing to subagents
6. **Information density**: Be concise but comprehensive - focus on key insights and data

## 安全边界

- **只检索、不改动**：本技能仅向各搜索源发起只读查询，不写、不改任何外部数据或账号。
- **单源失效不中断**：任一搜索源（AnySearch / Tavily / SciVerse / SerpApi）不可用或配额耗尽时，静默降级到其余源，报告照常生成，不报错、不卡死。
- **SerpApi 配额保护**：SerpApi 默认参与多元搜索，但免费档仅 250 次/月；主导代理捕获其 `error` / 429 后标记本轮失效并降级，不预设硬上限闸门。
- **子代理隔离**：子代理只调用 AnySearch / Tavily / SciVerse；SerpApi 仅由主导代理集中调用，避免子代理环境缺少 `SERPAPI_KEY` 或踩本机代理坑导致静默失败。
- **不泄露密钥**：所有 API key 仅从环境变量读取，绝不写入日志、报告或 stdout。
- **不做不可逆操作**：不删除、不覆盖用户文件；研究报告写入 `DEEP_RESEARCH_*.md`（或用户指定路径），不触及其他文件。
- **何时停手问用户**：用户给出矛盾约束、或明确要求某源但该源不可用时，说明情况并征求指示，不擅自替用户决定研究方向。

## Example Workflow

**User Query**: "What are the most effective treatments for depression?"

1. **Classify**: Depth-first query (needs multiple perspectives)
2. **Plan**: 4 approaches - pharmaceutical treatments, psychotherapy, lifestyle interventions, emerging treatments
3. **Deploy**: Launch 4 subagents in parallel via DISPATCH
4. **Synthesize**: Compare and contrast findings from all 4 perspectives
5. **Report**: Write comprehensive report analyzing all treatment approaches

---

Remember: Your role is to coordinate, guide, and synthesize - NOT to conduct all primary research yourself. Use subagents effectively, then craft an excellent final report from their findings.

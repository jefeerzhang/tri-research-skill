# Tri Research Skill

> 多源并行、中英双补、带可核验引用的深度研究工作流。

[![Version](https://img.shields.io/badge/version-5.6.0-blue)](skills/tri-research/CHANGELOG.md)
[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-tri--research-blueviolet)](skills/tri-research/SKILL.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](skills/tri-research/LICENSE)

## 核心能力

Tri Research 由主导代理规划和综合，并行派发独立研究子代理。它支持四个可选外部后端，以及宿主框架提供的 Runtime WebSearch：

| 渠道 | 调用者 | 主要用途 | 不可用时 |
|---|---|---|---|
| AnySearch | 子代理 | 通用网页、批量检索、正文提取 | 跳过 |
| Tavily | 子代理 | 深度网页搜索与提取 | 跳过 |
| SciVerse | 子代理 | 学术论文、语义片段、引用元数据 | MCP 缺失时尝试 Node CLI，再失败则跳过 |
| SerpApi | 主导代理 | 中英文 Google 与 Google Scholar 补强 | 跳过 |
| Runtime WebSearch | 主导代理 | 宿主框架内置补充渠道 | 使用其余可用渠道 |

计数规则是 `4 个可选外部后端 + 1 个运行时渠道`。发现命令或检测到环境变量不等于可用，只有轻量真实查询成功才标记为 `available`。

## v5.6.0 调度防护

- 使用跨平台 Python 状态机约束 `S0 -> S1 -> S2 -> S3 -> DONE`，并用显式 session id 隔离并发研究。
- 每轮研究只允许一次子代理派发；进入 `S2` 后禁止重新派发。
- 每个子代理在自己的进程内预检 AnySearch、Tavily 和 SciVerse，不复用主进程的凭据判断。
- 独立来源采用 `Promise.allSettled` 或框架等价语义，单源失败不会丢弃其他源的成功结果。
- 凭据、配置或配额错误触发来源级熔断，本子任务不再重试该来源，也不会因此派生或重新派发代理。
- 子代理限制为 8 分钟和 20 次工具调用；6 分钟后停止扩展检索并返回已有结果。
- 最终报告必须通过引用闭环、来源元数据、中英覆盖和渠道状态验收，才能进入 `DONE`。

## 工作流

```text
用户确认或直接给出研究问题
  -> 真实探测搜索渠道并报告一次状态
  -> S0: 确认主题、双语关键词、时间范围
  -> S1: 评估、分类、规划
  -> 主导代理执行 SerpApi / Runtime WebSearch 补强（可用时）
  -> S2: 一次性并行派发 1-6 个子代理
       -> 子代理本地预检 AnySearch / Tavily / SciVerse
       -> 故障隔离并行检索，中英双补
       -> 单源失败熔断，保留其余结果
  -> S3: 主导代理综合、写报告、加引用、验收
  -> DONE
```

简单问题使用 1 个子代理，非简单问题使用 2-6 个。主导代理负责最终综合与写作，不把最终报告再次委派出去。

## 安装

安装主技能：

```bash
npx skills add jefeerzhang/tri-research-skill
```

安装可选搜索后端：

```bash
npx skills add LearnPrompt/anysearch
npx skills add https://sciverse.space
```

Tavily 通过宿主 MCP 配置。SerpApi 使用仓库中的 `skills/serpapi`，从 `SERPAPI_KEY` 读取凭据。SciVerse 从 `SCIVERSE_API_TOKEN` 读取凭据，需要 Node.js 18 或更高版本来运行 CLI fallback。

所有密钥只从环境变量读取，不写入仓库、日志或研究报告。

## 使用

```text
tri-research 人工智能与劳动分配
```

也可使用 `多元研究`、`多源研究`、`深度研究`、`研究报告` 或 `文献综述` 等触发词。研究开始前会确认主题、中英文关键词和时间范围；用户直接给出完整约束时可按原请求继续。

默认输出：

```text
DEEP_RESEARCH_<TOPIC>_<YYYY-MM-DD>.md
```

报告包含 `TL;DR`、结构化正文、句末 `[N]` 引用、参考文献，以及每条来源的 URL、Tier 和 `Found by` 元数据。

## 搜索降级

| 状态 | 含义 | 行为 |
|---|---|---|
| `available` | 轻量真实查询成功 | 参与本轮研究 |
| `unavailable` | 未安装、未暴露、无凭据或网络失败 | 本轮跳过 |
| `quota_exhausted` | HTTP 429 或服务商明确返回用量上限 | 本轮熔断，不重试 |

任一单源失败都不阻断报告。所有渠道均不可用时，流程会明确说明阻塞，不伪造来源。

## 真实回归测试

2026-07-20 以“人工智能与劳动分配”为主题完成端到端回归：

| 检查项 | 结果 |
|---|---|
| 子代理派发 | 3 个一次性并行派发，3/3 完成 |
| 子代理收敛 | 每个 2 个 OODA 循环，约 2-5 分钟完成 |
| 派生与重派发 | 派生代理 0，重复派发 0 |
| 循环安全 | 空循环 0，死循环 0 |
| 状态机 | 仅一次 `SUBAGENTS_DISPATCHED`，最终 `DONE` |
| 自动化测试 | 15/15 通过 |

本轮后端状态：

- AnySearch：可用。
- SciVerse：主代理和 2/3 子代理可用；1 个子代理未继承凭据，按设计熔断并降级，未触发重派发。
- Tavily：`quota_exhausted`，按设计跳过。
- SerpApi：测试进程未检测到凭据，因此本轮未验证真实查询。
- Runtime WebSearch：当前宿主未暴露。

因此，本轮验证的是“核心调度、真实子代理工作、来源故障隔离和降级流程全部跑通”，不宣称所有外部来源均已成功调用。

## 测试

Windows / PowerShell 必须使用已配置的 conda Python：

```powershell
& 'C:\Users\jefeer\an\python.exe' -m unittest discover -s 'skills\tri-research\tests' -v
```

验证生成的研究报告：

```powershell
& 'C:\Users\jefeer\an\python.exe' 'skills\tri-research\scripts\validate_report.py' '<report.md>' --min-sources 12
```

## 文件结构

```text
tri-research-skill/
|-- README.md
|-- skills/
|   |-- tri-research/
|   |   |-- SKILL.md
|   |   |-- README.md
|   |   |-- CHANGELOG.md
|   |   |-- test-prompts.json
|   |   |-- scripts/
|   |   |   |-- state_machine.py
|   |   |   |-- state_machine.sh
|   |   |   `-- validate_report.py
|   |   `-- tests/
|   |       |-- test_skill_contract.py
|   |       |-- test_state_machine.py
|   |       `-- test_validate_report.py
|   |-- research-subagent/
|   |   `-- SKILL.md
|   |-- citations/
|   |   `-- SKILL.md
|   `-- serpapi/
|       |-- SKILL.md
|       `-- scripts/serpapi_cli.py
`-- assets/screenshots/
```

## License

MIT

# Tri Research Skill

> 多源并行、中英双补、带可核验引用的深度研究流程。

当前版本：`5.7.0`

## 能力边界

Tri Research 可使用四个可选外部搜索后端，并在运行时支持时使用内置 WebSearch 兜底：

| 渠道 | 调用者 | 作用 | 缺失时 |
|---|---|---|---|
| AnySearch | 子代理 | 通用网页、批量搜索、正文抓取 | 跳过 |
| Tavily | 子代理 | 深度网页搜索与提取 | 跳过 |
| SciVerse | 子代理 | 学术论文、语义片段和引用元数据；MCP 缺失时使用 Node CLI | 跳过 |
| SerpApi | 主导代理 | 中文/英文 Google 与 Scholar 补强 | 跳过 |
| Runtime WebSearch | 主导代理 | 框架内置兜底 | 使用剩余渠道 |

这里的计数规则是：`4 个可选外部后端 + 1 个运行时渠道`。不能把“配置了 key”或“发现了命令”当成可用；轻量真实调用成功才算 `available`。

## 适用场景

- 需要 10 个以上来源的研究报告
- 需要中文与英文证据互补
- 需要同时覆盖学术文献、政策文件、机构报告和网页资料
- 需要从多个相互独立的视角并行研究

简单事实查询、代码调试和本地代码库问题不应触发本技能。

## 输出

默认输出带唯一日期后缀的 Markdown 文件：

```text
DEEP_RESEARCH_<TOPIC>_<YYYY-MM-DD>.md
```

报告必须包含：

- `TL;DR` 与结构化正文
- 具体数据、日期与不确定性说明
- 正文句末 `[N]` 引用
- `参考文献` 章节
- 每条来源的 URL、`Tier` 和 `Found by`

主导代理负责撰写完整报告并加入引用。`citations` 技能可做可选复核，但不是报告完成的前置依赖。

## 工作流

```text
用户确认或直接给出研究问题
  -> 真实探测搜索渠道并报告一次状态
  -> 初始化带 session id 的状态机
  -> S0: 确认主题、双语关键词、时间范围
  -> S1: 评估、分类、规划
  -> 主导代理执行 SerpApi/WebSearch 补强（可用时）
  -> S2: 并行派发子代理
  -> S3: 汇总、写报告、加引用、验收
  -> DONE: 仅在报告文件存在且验收通过后进入
```

非简单问题使用 2-6 个子代理；简单问题使用 1 个。每个子代理必须覆盖中文与英文查询，并在 8 分钟内返回。

调度采用故障隔离：子代理各自预检后端，单源失败不丢弃其他源输出，也不触发重新派发。凭据、配额或配置失败只记录一次，然后该子代理跳过对应来源。

## 状态机

状态机实现位于 `scripts/state_machine.py`。它使用显式 `--session` 隔离并发研究，状态数据写入 `TRI_RESEARCH_STATE_DIR` 或系统临时目录，不写入技能安装目录。

PowerShell 下先激活获准的 conda 环境，并设置两个可移植路径变量：

```powershell
$env:CONDA_PYTHON = (Get-Command python).Source
$env:TRI_RESEARCH_HOME = (Resolve-Path '<tri-research-install-dir>').Path
$state = Join-Path $env:TRI_RESEARCH_HOME 'scripts\state_machine.py'
$session = 'ai-labor-allocation'

& $env:CONDA_PYTHON $state --session $session init
& $env:CONDA_PYTHON $state --session $session set_params '{"topic":"人工智能与劳动分配","time_range":"all"}'
& $env:CONDA_PYTHON $state --session $session advance S1
& $env:CONDA_PYTHON $state --session $session check
& $env:CONDA_PYTHON $state --session $session advance S2
& $env:CONDA_PYTHON $state --session $session advance S3
& $env:CONDA_PYTHON $state --session $session advance DONE --report '<report.md>' --min-sources 12
```

进入 `DONE` 时，状态机必须实际读取并验收报告；通过后在状态文件中记录报告路径、SHA-256、来源门槛和验收时间。缺报告或验收失败都会保持 `S3`。

Unix 环境可调用 `scripts/state_machine.sh` 兼容包装器，也可直接运行 Python 实现。

## 搜索降级

预检状态分三类：

| 状态 | 含义 | 行为 |
|---|---|---|
| `available` | 轻量真实查询成功 | 参与本轮研究 |
| `unavailable` | 未安装、未暴露、无 key 或网络失败 | 跳过 |
| `quota_exhausted` | HTTP 429 或服务商明确返回用量上限 | 本轮不再重试 |

任一单源失败都不阻断报告。所有渠道都不可用时，向用户说明阻塞，不伪造来源。

## 中英双补

每个研究子问题都必须至少包含一轮中文检索和一轮英文检索：

- 中文：覆盖中国制度背景、中文实证和本土政策材料
- 英文：覆盖跨国机制、同行评审论文和国际机构证据

最终报告应说明哪些渠道参与、哪些渠道降级，以及中英来源是否都达到覆盖要求。

## 安装

```bash
npx skills add jefeerzhang/tri-research-skill
```

可选配置：`ANYSEARCH_API_KEY`、`TAVILY_API_KEY`、`SERPAPI_KEY`。SciVerse 使用 `npx skills add https://sciverse.space` 安装，并从 `SCIVERSE_API_TOKEN` 读取凭据；宿主没有 SciVerse MCP 时自动调用技能自带的 Node.js 脚本。密钥只从环境读取，不写入日志或报告。

## 测试

```powershell
& $env:CONDA_PYTHON -m unittest discover -s (Join-Path $env:TRI_RESEARCH_HOME 'tests') -v
```

测试覆盖状态转换、非法跳转、重复初始化、并发会话隔离、参数 JSON、路径污染和技能契约一致性。

报告生成后必须运行验收器：

```powershell
& $env:CONDA_PYTHON (Join-Path $env:TRI_RESEARCH_HOME 'scripts\validate_report.py') '<report.md>' --min-sources 12
```

## 文件结构

```text
tri-research/
|-- SKILL.md
|-- README.md
|-- CHANGELOG.md
|-- test-prompts.json
|-- scripts/
|   |-- state_machine.py
|   |-- state_machine.sh
|   `-- validate_report.py
`-- tests/
    |-- test_state_machine.py
    |-- test_skill_contract.py
    `-- test_validate_report.py
```

## License

MIT

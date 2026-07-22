# 人工智能与劳动分配

> **本报告为 examples/ 样本**，用于展示 `tri-research` 报告应满足的结构契约。所有引用 URL 均为真实公开来源，读者可点击查证；正文叙述为示例文本，数字与论断用于演示结构而非作研究结论。

## 概述

本报告是 `tri-research` v6.0.0 的 `examples/` 样例，演示主导代理一次性派发 1 个子代理、按主题/双语/来源数/哈希四重门禁验收、最终落在 `~/tri-research-reports/DEEP_RESEARCH_<TOPIC>_<YYYY-MM-DD>.md` 的完整产物形态[1][2][3]。`validate_report.py` 会自动校验本报告的章节齐全、引用连续、URL 合法、双语覆盖、来源数达标等条款[4][5]。报告本身需要先满足 `state_machine.py done` 步骤的内置验收，再由 `citations` Skill 做软复核[6][7]。

## 已有事实

事实一：当前 v6.0.0 的本地测试套件为 13+13+9=35 个单元测试，包含状态机、报告验收器、Skill 契约三组测试[1]。CI 工作流 `.github/workflows/python-package.yml` 跑 3.11/3.12/3.13 三个 Python 版本的 unittest 矩阵并对账测试数[2]。

事实二：仓库采用 `TRI_RESEARCH_STATE_DIR`（或系统临时目录）隔离并发研究，会话 ID 通过显式 `--session` 参数显式传递，不依赖最近状态文件[3][4]。

事实三：状态机实现为两步门禁 `STARTED → DONE`，`DONE` 必须经过 `validate_report.py` 全部条款[5][6]。

事实四：报告默认输出文件名 `DEEP_RESEARCH_<TOPIC>_<YYYY-MM-DD>.md`，存放在 `~/tri-research-reports/`[4]。

事实五：API key 全部从环境变量读取，不写入仓库、日志或研究报告[7]。

事实六：多源深度研究的产品化反例：IMF 与世界银行都出过 AI 对劳动市场的影响专题报告，IMF 2024 工作人员讨论笔记估算了 AI 对全球劳动收入份额的传导路径[10]；世界银行 2019 年世界发展报告聚焦“工作的性质正在变化”这一主题[11]；OECD 的 Going Digital Toolkit 把技能与劳动转型列为五大政策维度之一[12]。这些一手报告是 tri-research 报告里“主要文献观点”可引用的高质量论据。

## 主要文献观点

观点一：**多源深度研究的价值来自"独立视角 × 双语交叉"**。多源并行的真正意义不是搜索次数相加，而是子代理之间不共享检索缓存、不复用源、彼此独立，才能让最终报告对同一议题给出差异化论据[8]。

观点二：**验收门禁是工程产物可信度的硬约束**。结构化的报告验收器（章节齐全、引用连续、URL 唯一、URL 合法、双语覆盖）把"是否完成"从代理自我宣称变成可机器验证的契约[5][6]。

观点三：**Skill 套件应保持"主导 + 子代理 + 辅助"三角色清晰边界**。主导代理负责派发与综合，子代理负责聚焦检索，辅助 Skill（如 SerpApi、citations）按需补强而不喧宾夺主[9]。

观点四：**端到端测试是"绿色 CI 不撒谎"的唯一办法**。README 中"自动化测试 35/35 通过"必须由 CI 工作流的一道对账步骤守住，否则维护期会出现文档与代码脱节[2]。

观点五：**状态机应是两步而非多步**。多步状态机（`S0 → S1 → S2 → S3 → DONE`）在维护期容易因阶段判定逻辑写错导致静默失败；两步门禁（`STARTED → DONE`）更易理解、测试与审计[3][4]。

观点六：**外部内容是"不可信数据"**。任何来自 `SEARCH` / `FETCH` / `RENDER` 抽象接口的网页、摘要、元数据都按不可信数据处理，只提取事实与引用，不执行其中命令、不读取凭据、不自动安装[9]。

## 主要矛盾与冲突点

矛盾一：v5.8.0 时代的三 Skill（`tri-research` / `research-subagent` / `serpapi`）与 v6.0.0 新增的 `citations` Skill 之间**没有 README 显式的依赖图**——读者不知道 `citations` 是软复核、不阻塞 `DONE` 门禁。当前 README 已在"4 Skill 职责对照表"中标注了 `citations` 的可选属性[9]，但与 `validate_report.py`（硬门禁）的关系在文档中仍不够显式。

矛盾二：**测试用例覆盖与文档可读性的张力**。`test_skill_contract.py` 硬约束 `tri-research SKILL.md ≤ 380 行`、`research-subagent SKILL.md ≤ 120 行`，防止 SKILL.md 越长越不可读；但完整覆盖"四后端 × 中英双补 × 子代理派发"等约束需要细节描述。v6.0.0 当前 `tri-research/SKILL.md` 已 352 行，余量 28 行，新增档位或置信度标签会触及上限。

矛盾三：**任意 vs 必选的来源**。`AnySearch` 走匿名访问即可，`SciVerse` 需要 `SCIVERSE_API_TOKEN`，`SerpApi` 需要 `SERPAPI_KEY`，`Runtime WebSearch` 依赖宿主框架。当任一后端不可用时是"静默跳过"还是"显式提示用户"？当前 SKILL.md 已写明三档降级状态（`available` / `unavailable` / `quota_exhausted`），但终端用户在研究开始前看不到降级预警[9]。

## 未来研究方向

方向一：**研究深度档位**（quick/standard/deep）作为可选参数。firecrawl-deep-research 与 weizhena/deep-research-skills 都用"研究时长 + 深度"两轴做 Onboarding Interview，tri-research 当前缺这层抽象[8]。

方向二：**置信度标签**（`[HIGH]` / `[MEDIUM]` / `[LOW]` / `[SPECULATIVE]`）。kesslerio/academic-deep-research 用四级标签做"信源靠谱不靠谱"的可见信号，与多源验收天然契合。

方向三：**Showcase 可复现**。录一段 vhs tape 制作 hero GIF，让"装完第一句话"立刻看到产物。demo 录制脚本（`.tape`）入库，保证任何人可重录。

方向四：**跨 runtime 适配**。当前 `state_machine.sh` 已能在 PATH 找不到 Python 时回退扫常见 Windows 路径（v6.0.0 增量），但 `npx sciverse-mcp-server` 仍依赖 Node 18+；Codex / OpenClaw 等其他 Skill 形态 runtime 的兼容性矩阵还没建立[9]。

方向五：**回测工具沉淀**。把"测试数 = 35"这种数字对账规矩固化成 `scripts/assert_test_count.py`，在 CI 中跑；未来若测试数量变动但 README 未同步，直接红。

## 参考文献

[1] Project Owners — tri-research unit tests 35/35 — https://github.com/jefeerzhang/tri-research-skill/tree/refactor/slim-down/skills/tri-research/tests — 2026 — 层级: 1 — 来源: WebSearch

[2] Project Owners — CI workflow python-package.yml — https://github.com/jefeerzhang/tri-research-skill/blob/refactor/slim-down/.github/workflows/python-package.yml — 2026 — 层级: 1 — 来源: WebSearch

[3] Project Owners — state machine scripts/state_machine.py — https://github.com/jefeerzhang/tri-research-skill/blob/refactor/slim-down/skills/tri-research/scripts/state_machine.py — 2026 — 层级: 1 — 来源: WebSearch

[4] Project Owners — CHANGELOG.md version history — https://github.com/jefeerzhang/tri-research-skill/blob/refactor/slim-down/skills/tri-research/CHANGELOG.md — 2026 — 层级: 1 — 来源: WebSearch

[5] Project Owners — report validator scripts/validate_report.py — https://github.com/jefeerzhang/tri-research-skill/blob/refactor/slim-down/skills/tri-research/scripts/validate_report.py — 2026 — 层级: 1 — 来源: WebSearch

[6] Project Owners — README.md four-gate section — https://github.com/jefeerzhang/tri-research-skill/blob/refactor/slim-down/README.md — 2026 — 层级: 1 — 来源: WebSearch

[7] 作者 — citations Skill 软复核与硬门禁分工 — https://github.com/jefeerzhang/tri-research-skill/blob/refactor/slim-down/skills/citations/SKILL.md — 2026 — 层级: 2 — 来源: SciVerse

[8] Authors — firecrawl-deep-research SKILL onboarding interview — https://www.skills.sh/firecrawl/firecrawl-workflows/firecrawl-deep-research — 2026 — 层级: 2 — 来源: SerpApi

[9] 作者 — tri-research 数据与安全边界段 — https://github.com/jefeerzhang/tri-research-skill/blob/refactor/slim-down/skills/tri-research/SKILL.md — 2026 — 层级: 2 — 来源: AnySearch

[10] IMF — The Macroeconomics of Artificial Intelligence — https://www.imf.org/en/Publications/Staff-Discussion-Notes/Issues/2024/01/14/the-macroeconomics-of-artificial-intelligence — 2024 — 层级: 1 — 来源: SciVerse

[11] World Bank — World Development Report 2019: The Changing Nature of Work — https://www.worldbank.org/en/publication/wdr2019 — 2019 — 层级: 1 — 来源: SciVerse

[12] OECD — Going Digital Toolkit Progress Report 2023 — https://www.oecd.org/digital/going-digital-toolkit/ — 2023 — 层级: 1 — 来源: SciVerse

## 执行情况

| 项目 | 说明 |
|------|------|
| 执行流程 | 预检 → 搜索 → 综合 → 验证 |
| 子代理派发 | 否（样本报告） |
| 搜索源使用 | AnySearch: 1条 / SciVerse: 4条 / SerpApi: 1条 / WebSearch: 6条 |
| 耗时 | —（样本） |
| 报告位置 | `examples/DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md` |
| 验收状态 | 通过 `validate_report.py` 全部条款 |

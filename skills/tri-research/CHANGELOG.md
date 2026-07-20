# Changelog

All notable changes to the Tri Research Skill will be documented in this file.

## [5.3.0] - 2026-07-20

### Changed
- **"四源"→"多元"重命名**：技能定位从固定四源升级为可扩展的多元搜索架构，呼应未来可继续增加搜索源。
  - frontmatter `description` 改为 "multiple search backends ... (extensible)"；`triggers` 移除 `四源研究/三源研究/三源搜索`，新增 `多元研究/多源研究`。
  - SKILL.md 正文："four search backends"→"multiple search backends (currently ... extensible)"；"四源/三源"指代统一改为"多元/其余源/三个源"。
  - README 首屏钩子改为"多元搜索并行、中英双补"，降级表与可用性流程图同步"多元"。
  - 历史版本记录（v4/v5 的"三源"）保留为事实数据，不回改。

### Added
- **全局双语纪律段**：从 SerpApi 段与子代理段抽离出统一的"全局双语纪律（所有源、所有代理通用）"，明确中英双补是贯穿所有源、父子代理的统一硬约束，消除约束分散导致的维护漂移。

## [5.2.0] - 2026-07-20

### Added
- **中英双语强制约束（四源一致）**：子代理三源检索与父代理 SerpApi 补强，均须中英双补，不得只抓中文。
  - 子代理搜索源约束段新增"无论用哪源，检索与抓取必须中英双补……只抓单语种视为流程缺陷"。
  - SerpApi 调用约束段新增第 3 条：补强必须中英双补（中文轮 `hl=zh-cn`+`gl=cn`、英文轮 `hl=en`+`gl=us`），两轮结果都并入综述并标注"中英双补"。
  - Example Task Description 模板新增 `Language coverage REQUIRED` 段。

### Changed
- SKILL.md frontmatter `version` 同步至 5.2.0（此前漏更至 5.1.0）。
- README 搜索工具依赖表补 SerpApi 行，与"四源"首屏钩子一致。

## [5.1.0] - 2026-07-20

### Added
- **四源并行搜索架构**：在原有三源（AnySearch + Tavily + SciVerse）基础上，新增 **SerpApi** 作为第四源，强化中文 Google / Google Scholar / 100+ 垂直 SERP 的精准抓取。
- **SerpApi 调用约束段**：明确第四源仅由主导代理集中调用（不派发给子代理，规避子代理 env/代理坑），在合成报告前集中补强。
- **配额静默降级**：SerpApi 免费档 250 次/月；默认参与四源，配额耗尽或密钥缺失时捕获 `error` 字段后静默降级到其余三源，报告照常生成并在末尾注明，不中断不报错。
- **四源可用性检测**：前置检测表新增 SerpApi 项（`[N/4]`），检测命令指向 `serpapi` skill 的 CLI。
- **测试 prompt 扩充**：test-prompts.json 新增 `serpapi-fourth-source` 与 `serpapi-quota-degrade` 两个用例，覆盖第四源集成与配额降级。

### Changed
- frontmatter `description` 与 `triggers` 更新为"四源"；README 首屏、降级表、可用性流程图同步四源表述。
- "39来源/67%互补率"历史数据保留于 v5.0.0 记录，四源实际覆盖以运行时检测为准。

## [5.0.0] - 2026-07-20

### Added
- **三源并行搜索架构**：AnySearch + Tavily + SciVerse 三个搜索后端并行工作
- **框架无关抽象接口**：SEARCH/FETCH/RENDER/DISPATCH 抽象层，适配任意 Agent 框架
- **前置依赖声明**：frontmatter 中的 `dependencies` 字段，明确三个搜索工具的安装方式和降级策略
- **8分钟超时约束**：子代理必须在 8 分钟内完成搜索，防止卡死
- **错误处理指南**：9 种错误场景 + 降级优先级链
- **反例黑名单**：8 条"不要做什么"的明确约束
- **触发词列表**：tri-research、三源研究、三源搜索、深度研究等
- **测试用例**：test-prompts.json，含 5 个测试查询 + 8 项验证清单
- **README**：产品说明 + 五轮迭代对比数据 + 架构图
- **CHANGELOG**：版本记录（本文件）
- **LICENSE**：MIT 许可证
- **Tier 分级**：来源按可信度分为 Tier 1/2/3
- **来源溯源**：每个来源标注由哪个搜索工具发现（Found by）

### Changed
- 重命名：`deep-research` → `tri-research`
- 路径硬编码改为环境变量 `${ANYSEARCH_SKILL_DIR}`

### 实测数据（v5）
- 来源总数：39（v1 为 24，提升 63%）
- Tier 1 来源：25
- 2024-2025 文献：15
- 顶刊文献：6
- 三源互补率：67%（26/39 来源来自单一工具独占）
- 子代理耗时：1.4-2.4 分钟（全部在 8 分钟约束内）

## [4.0.0] - 2026-07-20

### Added
- AnySearch CLI 工具集成
- 三源搜索（AnySearch + Tavily + SciVerse）

### Issues
- 无时间约束，1 个子代理超时被中止

## [3.0.0] - 2026-07-20

### Changed
- 搜索工具从 web_search 替换为 Tavily + SciVerse

### Added
- SciVerse 学术论文搜索
- Tavily 深度搜索模式

## [2.0.0] - 2026-07-20

### Changed
- 框架无关化重构：工具名改为抽象接口（SEARCH/FETCH/RENDER/DISPATCH）
- 功能不变，仅改变技能文件写法

## [1.0.0] - 2026-07-20

### Initial
- 从 GitHub 仓库 `simple_claude_deep_research_agent` 克隆
- 使用 web_search + web_fetch + Playwright 作为搜索工具
- 三种查询类型：直接查询、广度优先、深度优先
- Lead Agent + Subagent + Citations Agent 三角色架构

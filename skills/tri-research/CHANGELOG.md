# Changelog

All notable changes to the Tri Research Skill will be documented in this file.

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

# Changelog

All notable changes to the Tri Research Skill will be documented in this file.

## [6.3.0] - 2026-07-29

### Fixed
- **文档六源表对齐**：skill README / 根 README / `runtime-adapters.md` / 合约测试与 `SKILL.md` 统一为六源（AnySearch / Tavily / SciVerse / Exa / SerpApi / Runtime WebSearch）；Tavily 仅 Lead Agent；参考文献 `来源:` 字段含 Tavily

### Added
- **大纲适配（借鉴 deep-research Phase 3.5）**：第七步综合时对比计划结构 vs 实际证据，调整幅度 ≤50%（超出时须在执行情况标注原因），证据驱动不凭空添加。调整记录写入执行情况。
- **多波次检索（借鉴 deep-research Wave 设计）**：第二步检索计划标注波次：Wave 1 广覆盖 → 质量门判定 → Wave 2 精准补漏 → Wave 3（deep 模式）。
- **综合子代理（借鉴 deep-research Synthesis Agent）**：第七步 deep 模式（来源 >20 条）可选派 Synthesis 子代理预写各维度摘要，Lead Agent 整合进报告。仅预写维度摘要，不代写最终报告。
- **优雅降级（借鉴 deep-research）**：安全边界增加整波失败处理——缩减报告 + 执行情况标注降级 + 受影响章节置信降 `[低]`；零来源时告知用户停止。
- **声明-来源匹配核验（借鉴 deep-research Phase 3.1）**：第六步增加二级核验，选 5-10 条核心结论检查引用来源是否实际支撑声明，判定 SUPPORTED/PARTIAL/UNSUPPORTED 三级。

### Changed
- SKILL.md 因新增功能增至 383 行（合约上限 450 行）

## [6.2.0] - 2026-07-29

### Added
- **研究上下文预加载**：研究开始前自动查找 `RESEARCH_CONTEXT.md`（项目根目录或 `~` 下），加载后预填研究偏好（默认受众、深度、时间窗口、术语表），减少每次研究的重复澄清。研究完成后可选择保存本次偏好供下次复用。
- **研究意图澄清（新第一步）**：在源检测前增加 5 维度澄清步骤（目标/受众/深度/时间/语言），只问计划推不出来的维度，最多 3 个问题，用户一句话回复。与 `RESEARCH_CONTEXT.md` 联动，已有答案的维度自动跳过。
- **来源内容核验（新第六步）**：结果确认后、撰写报告前增加内容级核验步骤。学术来源全部用 SciVerse SDK 按 DOI/标题核验存在性与元数据；网页来源抽查 5-10 条用 `extract` 确认内容支撑。判定三级：✅ 通过（条目加 `核验: ✅`）/ ⚠️ 部分匹配（按数据库实际修正）/ ❌ 未找到（不得进入参考文献，支撑结论降级或删除）。核验记录写入执行情况（核验 N / 通过 N / 修正 N / 剔除 N）。默认 Lead Agent 直接核验，来源 > 25 条可派核验子代理（含任务模板）。**铁律：严禁凭训练记忆补全查不到的文献信息**。解决 `validate_report.py` 只查格式、查不出编造文献的漏洞。
- **置信标签（与来源层级联动）**：「已有事实」每条结论末尾必须标注 `[高]` / `[中]` / `[低]`。`[高]` 需 3+ 独立来源一致且至少 1 个层级 1/2 来源；纯层级 3 堆叠封顶 `[中]`；核验剔除的来源不计入支撑数。规则见 SKILL.md「置信标签」章节。
- **质量门自动判定**：第五步结果确认时附带 5 项自动检查（来源数达标/维度覆盖均衡/反面视角覆盖/语言覆盖/高层级占比≥30%且≥3条），不通过时明确标红薄弱维度，供用户知情决策，不硬拦。
- **Gap-Fill 专用子代理**：补搜时不再重跑整个维度，改为派 Gap-Fill 子代理精准补漏。模板明确告知「已有哪几条、缺什么证据、去哪里找」，与普通检索子代理分离。
- **红队自批判**：第七步动笔前，Lead Agent 内部自问三个问题——缺什么视角？哪个结论证据最弱？反对者会怎么攻击？批判是内部过程，不写入报告正文；产出通过置信标签降级和矛盾章节内化到报告中。
- **矛盾保留规则**：去重合并时发现子代理结论相反，**禁止静默二选一**——两个结论都保留写入「主要矛盾与冲突点」，正文中引用双方来源说明分歧，有第三方佐证的结论置信度提升。

### Changed
- **SKILL.md 压缩**：从 621 行压缩至 377 行（减少 39%），所有实质性规则和逻辑不变。压缩手段：5 个工具调用子节合并为统一速查表，交互式引导合并为安装表，子代理模板去重复说明，质量门去掉冗余示例输出，Gap-Fill/核验模板精简，红队+去重+矛盾规则压缩为要点，报告模板精简，增量研究压缩为流程链。
- 流程从 5 步扩展为 7 步 + 1 补漏子步骤：研究意图澄清 → 源检测 → 初始化 → 子代理派发 → 结果确认+质量门 → 来源核验+Gap-Fill → 红队批判+综合撰写
- 执行情况表格新增「来源核验」统计行和「思考程度」行
- 全文交叉引用统一修正（Step 3→第四步，核验→第六步等）

## [6.1.0] - 2026-07-23

### Changed
- **Tavily 调用方式从 MCP 改为 Python SDK**：主代理统一通过 `scripts/tavily_search.py` 调用 `tavily-python` SDK，与子代理的 `exa_search.py` 风格对齐；不再依赖 `mcp__tavily__*` 工具。

## [6.0.0] - 2026-07-22

### Added
- **交互式引导流程**：首次使用时逐个源检测 + 配置引导（AnySearch → SciVerse → SerpApi），用户可跳过任意源
- **首次使用引导输出**：研究开始前输出 `搜索源状态：AnySearch ✅/❌ | SciVerse ✅/❌ | SerpApi ✅/❌ | WebSearch ✅`
- **参考文献单行格式**：与 validate_report.py 正则对齐，必须含 `层级:` `来源:` `URL:` 三个关键字
- **执行情况表格**：从 bullet list 改为 Markdown 表格（7 行标准字段：流程/子代理/源使用/覆盖质量/维度覆盖/耗时/报告位置）
- **Tavily 重新列为独立的第 5 后端**（与 Runtime WebSearch 严格区分）：Tavily 是独立的搜索服务（需 `TAVILY_API_KEY`，通过 `tavily-python` SDK 调用，CLI 封装见 `tri-research/scripts/tavily_search.py`），Runtime WebSearch 是宿主内置抽象能力（实现不固定，可由 Tavily/Bing/Google/Brave 等任意引擎实现）。两者独立配置、独立降级、独立计费，**不能**把 Tavily 当作 Runtime WebSearch 的"实现"。
- **SciVerse 改为 Python SDK 必选路径**（**禁止 MCP 通道**）：v6.0.0 起 SciVerse **只走** `pip install sciverse` + `from sciverse import AgentToolsClient` + `SCIVERSE_API_TOKEN` 环境变量。**MCP 通道（`mcp__sciverse__semantic_search` 等）已弃用**——Proma 协作子会话实测不继承父会话 MCP 工具，是不可靠通道。`~/.claude/mcp.json` 里**不应**再包含 `sciverse` 段；`sciverse-mcp-server` npm 包**不再需要安装**。

### Fixed
- **报告范式修正**：从"列信息"（X 报告称…Y 报告称…）改为"凝练总结"（多源合起来说明什么洞察）
- **子代理任务描述模板压缩**：去掉 MCP 引用，数据源改为 Python SDK，8 条 requirements 合并为单段
- **脚本精简**：state_machine.py 从 374 行精简为两步门禁（STARTED → DONE），代码量减半
- **测试精简**：从 434 行 state_machine 测试精简为 13 项合约测试 + 验收器测试
- 子代理的 AnySearch 路由改为 CLI-only：直接运行 bundled `anysearch_cli.py` 的 `doc`、`batch_search` 和 `extract`，禁止宿主把 AnySearch 自动映射到 MCP 工具。
- 清理 `scripts/state_machine.py` 与 `scripts/validate_report.py` 末尾粘连的 shebang 与重复 docstring。
- 补齐缺失的 `scripts/state_machine.sh` 兼容包装与 `skills/citations/SKILL.md`，使文件结构与文档一致。
- 版本号统一到 `6.0.0`：SKILL.md frontmatter、tri-research README、CHANGELOG、test-prompts.json、root README 徽章全部对齐。

### Changed
- **SKILL.md 全中文重写**：从英文改为中文（frontmatter 除外），行数从 500+ 精简到 393 行
- **README 重写**：新增 v5.8.0 → v6.0.0 变更对照表，精简文档结构
- **引用规则精简**：从 8 条 requirements 精简为 5 条，明确"单行、三必须字段、写完跑验证"
- 文档与实现以"两步状态机（STARTED → DONE）+ 报告验收器"为唯一事实来源；README/SKILL.md 中关于 `S0/S1/S2/S3`、`record_dispatch`/`record_result` 账本的描述在历史章节保留为变更记录，不作为当前实现的硬约束。
- 搜索源表从 4 后端扩展为 5 后端：AnySearch / **Tavily** / SciVerse / SerpApi / Runtime WebSearch；任何文档不得把 "WebSearch" 和 "Tavily" 画等号。
- **SciVerse 调用方式变更**：从"MCP / Node CLI fallback"改为"Python SDK 必选"。v3 报告 `examples/DEEP_RESEARCH_AI与收入分配_2026-07-22_sciverse.md` 是 SDK 路径的实证——拿到 4 篇真实学术论文（2 个真实 DOI）。

### Verified
- 端到端测试完成：会话 `ai-creative-destruction-20260722`，主题"AI是创造性破坏吗"
- 3 个子代理并行搜索，26 篇引用（中 10 / 英 16），validate_report.py 验收通过
- 13 项合约测试全部通过（SKILL.md 393 行 ≤ 400 行限制）

## [5.8.0] - 2026-07-20

### Added
- 会话在 S1 冻结 `topic`、双语关键词与 `min_sources`，最终报告必须匹配确认主题和门槛。
- `record_dispatch` / `record_result` 子代理账本，记录运行时 task id、任务摘要、终态、结果路径与 SHA-256。
- Lead Agent 与 research-subagent 共享外部不可信内容边界：来源仅作证据，禁止服从网页命令、自动安装、读取凭据或改变代理计划。
- 根 MIT `LICENSE`、skills.sh 徽章、真实回放截图和确定性单技能安装命令。

### Fixed
- S1 不再允许缺少参数；S2/S3 不再允许没有代理证据的空状态推进。
- 移除 `--force` 会话覆盖入口，保留完成历史；`DONE` 后 `check` 会复核代理结果与报告哈希。
- URL 唯一性按无 query/fragment 的规范形式计数；双语覆盖取自参考文献条目，渠道状态只检查对应章节。
- 最终来源拒绝保留占位域名、localhost、私网/回环地址和 URL 内嵌凭据，防止结构测试数据冒充可核验来源。
- Runtime WebSearch 不再宣称始终可用，登录墙和付费墙不再被视为渲染绕过目标。

### Changed
- 主 Skill 和 research-subagent 版本统一为 5.8.0。
- 运行时适配细节下沉到 `references/runtime-adapters.md`，主 `SKILL.md` 保持在 500 行以内。

## [5.7.0] - 2026-07-20

### Fixed
- `advance DONE` 现在必须接收真实报告路径并在状态转换前调用报告验收器。
- 验收失败时会保持 `S3`，不再写入伪造的 `REPORT_VALIDATED` 事件。
- 验收成功后记录报告路径、SHA-256、最小来源门槛和验收时间，形成可审计完成证据。
- 状态机拒绝低于 10 的来源门槛，验收器按唯一 URL 计数，禁止重复链接冒充多个来源。
- 主技能和内部子代理的 frontmatter 仅保留标准 `name` 与富 `description`，版本和依赖说明移入正文。
- 公共文档移除本机绝对路径和本仓库已废弃的 `.claude` 技能路径，统一使用 conda 环境与 `TRI_RESEARCH_HOME`。

### Added
- 增加缺报告、无效报告、低来源门槛和重复 URL 的反例测试，并校验验收证据哈希。

## [5.6.0] - 2026-07-20

### Fixed
- 子代理必须本地预检后端，避免把主进程可用状态错误外推为凭据已继承。
- 并行源调用改为 failure-isolated / `allSettled` 语义，单源失败不再丢弃其他源的成功输出。
- 凭据、配置或配额失败按来源熔断，本子代理立即跳过该源剩余查询，不重试、不重新派发。

### Verified
- 3 个子代理一次性派发并全部返回，无子代理派生、无重复派发、无空循环或死循环。
- 每个子代理 2 个 OODA 循环后收束，完成时间约 2–5 分钟。

## [5.5.0] - 2026-07-20

### Fixed
- SciVerse 不再依赖宿主必须暴露 MCP；未暴露时自动使用官方 skill 的 Node.js CLI。
- 可用性探测改为验证 CLI 退出码、`biz_code: 0` 和 `hits`，避免“Token 已配置但后端不可达”的假阳性。
- 子代理必须保留 SciVerse 返回的 `doc_id`、题名与原文片段，确保学术证据可复现。

### Added
- 官方安装命令 `npx skills add https://sciverse.space` 与 `SCIVERSE_API_TOKEN` 配置说明。
- 中英文语义检索实测通过，MCP 缺失时 CLI fallback 可用。

## [5.4.0] - 2026-07-20

### Fixed
- 将 Bash 专用状态机改为跨平台 Python 实现；`state_machine.sh` 仅保留兼容转发。
- 使用显式 `--session` 隔离并发研究，移除“读取最近状态文件”造成的串会话风险。
- 将运行状态目录从 `TRI_RESEARCH_HOME` 分离为 `TRI_RESEARCH_STATE_DIR`，不再污染技能安装目录。
- 重复初始化默认报错，不再静默删除已有状态；增加原子写入和 session id 路径校验。
- 修正“最终报告不要引用”与验收清单要求引用之间的冲突，主导代理必须生成完整引用。
- 修正四个外部后端与运行时 WebSearch 被混称“四源/五源”的计数歧义。
- 工具预检改为轻量真实查询，区分 `available`、`unavailable`、`quota_exhausted`。

### Added
- 6 个状态机自动化测试，以及技能版本、引用、路径和测试主题的契约检查。
- “人工智能与劳动分配”端到端测试用例，要求中英双补和带引用 Markdown 报告。
- `validate_report.py` 报告验收器，检查章节、引用闭环、来源元数据、双语覆盖与渠道状态。

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

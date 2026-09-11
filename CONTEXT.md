# tri-research-skill

多源带引用深度研究 Skill 套件（主导代理 + 子代理 + 多搜索后端 + 报告验收）。

## Language

**Research Session**:
一次深度研究的生命周期容器，由 `state_machine.py` 的 `StateStore` 管理，经历 `STARTED → DONE`（可经 `add_dimensions` 进入 `EXTENDED`），以 `session_id` 标识。
_Avoid_: 任务、会话 id 混称

**Search Backend**:
一个可通过 CLI 调用的网页搜索适配器，满足 `_search_cli.Backend` interface（`probe` / `search` + flags + `env_file` 自报自家 `.env` 位置）。客户端装配（SDK 在场 → key 可解析 → 构建）只住在 `Backend.client()` 一处，失败抛 `ClientSetupError`（`SdkMissing` / `KeyMissing`），输出方言仍归各条命令；只有 key 持有者的后端（SerpApi）单用 `Backend.api_key()` 半边。必要性由 `Backend.requirement` 申报，就绪判定走 `Backend.readiness()`（与 `client()` 同一套 SDK→key 装配判断，住在 `require_setup`；SerpApi 另 `start_probe`）。分级见 `BackendRequirementLevel`。
_Avoid_: 搜索引擎、search provider 混称

**SearchBackendRegistry**:
深 Module，统一管理所有 Web 搜索类后端的注册、Result 归一与探活，interface 为 `register / get / list_backends / search / batch_search / check`。它**只转接**客户端装配（调 `Backend.client()`）而不另定一套规则。定位为**程序化 seam**（测试与直接 import 的调用方）；Agent 消费的命令行表面走 `_search_cli`，两条路不得混用错误契约。
_Avoid_: backend manager、search service

**SearchResult**:
Registry 对外暴露的饱和小接口，含 `title / url / snippet / content / score / published_date / engine_meta`，缺失为 `None`；截断上限（snippet / content 两个宽度）住在 `_search_cli`，两条泳道共读一份，不得各自写死数字。
_Avoid_: raw response、organic_results 直出

**KeyProvider**:
Seam 处的 Key 解析 Adapter，优先级 `cli --api_key > env > .env`，供所有 Search Backend 共用；正常入口是 `Backend.api_key()`，`.env` 位置由各后端经 `Backend.env_file` 申报，本模块不含任何技能目录布局知识。
_Avoid_: key loader、env helper 混称

**BackendSpec**:
声明式规格，描述「哪个 Search Backend 注册进了 Registry」——`name / backend`；调参旋钮住在 Backend 实例上。不携带 key 材料：`env_key` / `env_file` 是 Backend 自己的申报，同一信息两处维护就能彼此不同意。
_Avoid_: backend config 泛称

**BackendRequirementLevel**:
Search Backend 的三档必要性分级，以可执行枚举住在 `_search_cli.BackendRequirementLevel`（ADR-0011）：`required`（Exa / SciVerse：K+S——Key 可解析且 SDK 可 import；SerpApi：Key 可解析 + 轻量探活成功，见 ADR-0007）在 Research Session `start` 前由 `require_required_backends` 按描述符 `requirement` 字段强制，缺失/探活失败则 `StateError`、无用户降级逃逸；`recommended` 缺失仅黄字提醒但允许匿名降级（本波仍文档-only）；`optional` 缺失静默跳过。改档只改字段，不改 walker 正文。
_Avoid_: 必选/可选二分、优先级混称、文档-only 约束、在门禁里手抄各家常量

**Delivery Unit**:
开跑一次 Research Session 的最小安装集合：`tri-research` + `serpapi` 两个 skill（`research-subagent` 推荐，`citations` 可选）。只装 `tri-research` 不足以 `state_machine start`（SerpApi 是 `required`，代码住在兄弟 skill）。两 skill 的 scripts 路径耦合仍在，待 ADR-0015。见 ADR-0012 D1。
_Avoid_: 单技能安装即就绪、把 serpapi 写成可省略的辅助 skill、把路径耦合当成已解耦

**Managed Command**:
由 `_search_cli` 骨架**全权接管执行流程**的一类 extra 命令（当前：Exa `answer` / `contents`、Tavily `extract`）。骨架负责顺序（代理清理 → 经 `Backend.client()` 装配 → `invoke`（超时 / 重试 / 熔断）→ 错误 JSON 打印与退出码）；命令体只声明「用 client 发起哪一次 SDK 调用」并返回待打印结果，失败时抛带 echo 标记（`query` / `url`）的错误。与未托管命令（如 SerpApi 的 `doc` / `engines` / `export`，各自保留 `(args)` 签名与错误契约）通过 `Command` 上的 opt-in 开关区分。
_Avoid_: 托管任务、wrapped command、managed handler 混称

**Evidence Ledger**:
会话级 append-only 证据流水账，记录研究会话中每波搜索见过的 URL 及其出处（backend / query），与会话状态文件并列存放、以 `session_id` 标识；只追加不修改，是 Evidence Audit 的对账依据。Machine 后端（Exa / Tavily / SerpApi）在 `search` / `batch_search` 传入 `--session` 时于成功路径自动追加 `seen` 行，写入失败则 CLI 失败（ADR-0010）；无 `--session` 保持裸搜。
_Avoid_: 搜索日志、引用缓存、结果收藏混称

**Evidence Record**:
Evidence Ledger 的单条记录，只可能是两种 kind 之一：`seen`（搜索事件：backend / query / url / title / ts）与 `user_provided`（用户提供的资料：url / note / ts）；写入不去重——同一 URL 被多条 query 搜到就记多行。
_Avoid_: 引用记录、采纳标记（adopted）混称

**Evidence Audit**:
报告参考文献对 Evidence Ledger 的溯源对账：每条引用 URL 经统一归一化后必须在台账中命中（`user_provided` 与 `seen` 同等资格），作为 `done` 的硬门禁，untraced 即失败。失败文本只有一个家——`EvidenceAuditFailed` 持有 `untraced / total` 与那句计数，`audit` 命令与 `done` 门禁各自追加自己的半句（登记指引 / 明细列表），两处不得再手抄。
_Avoid_: 引用校验、格式验收混称（那是 Report Validation）、把门禁合并成单一 completion_gate（判定与对账的失败语义与修复路径不同）

**Report Parse**:
研究报告契约的唯一解析表面（`_report_parse.py`）：章节切分、参考文献字段、行内 span（code / bold / cite / conf）、围栏判定与 URL 方言。只回答「这份文本长什么样」，不回答「合不合格」——判定属 Report Validation，对账属 Evidence Audit，排版属 LaTeX/PDF 渲染器，三方共读同一份解析结果。
_Avoid_: 各家自持的正则、把任一消费方的解析当权威

**Report Validation**:
报告硬门禁集合，由 `validate_report.py` 强制（7 章节、引用闭环、双语、搜索源使用行等；「搜索源使用」点名名单见 ADR-0009：六源全点名，Tavily 可写 `0/跳过`），`validate → errors[]` 为其 test surface；语法一律读 `Report Parse`，本模块只留判定；`verify_proof_integrity` 为其完整性复核半区——按与建据一致的原始字节重算 SHA-256 并比对 DONE 指纹，区分 `ReportTamperedError`（内容变）与 `ReportMissingError`（文件不可读）。
_Avoid_: report check 泛称

**Google Scholar（间接能力）**:
不是独立 Search Backend——它是 SerpApi 经 `--engine google_scholar` 提供的**间接**能力。SerpApi 是 `required` 的**发现通道**；Google Scholar 的学术书目/语义面由 SciVerse 承担。
_Avoid_: 把 SerpApi 与 Google Scholar 混为一谈（接了 SerpApi ≠ 补了 Scholar）、把 Evidence/`来源:` 改名 "Google Scholar"

**SciVerse（学术 SDK 路径）**:
学术书目与语义检索的唯一 SD 路径（Python SDK `AgentToolsClient`，禁止 MCP），承担「学术面」。**不是** OpenAlex 的代名词——即使底层可能复用 OpenAlex 类覆盖，术语上不得把 SciVerse 改名为 OpenAlex。Required 门禁通过 `SciVerseReadiness` 描述符挂到与 Machine 后端同一轮询列表，**不是** Search Backend，不得注册进 `SearchBackendRegistry`（ADR-0006 / ADR-0011）。
_Avoid_: SciVerse 与 OpenAlex 混称、把 SciVerse 当成 Web Backend / 塞进 Registry

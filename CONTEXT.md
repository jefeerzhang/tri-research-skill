# tri-research-skill

多源带引用深度研究 Skill 套件（主导代理 + 子代理 + 多搜索后端 + 报告验收）。

## Language

**Research Session**:
一次深度研究的生命周期容器，由 `state_machine.py` 的 `StateStore` 管理，经历 `STARTED → DONE`（可经 `add_dimensions` 进入 `EXTENDED`），以 `session_id` 标识。
_Avoid_: 任务、会话 id 混称

**Search Backend**:
一个可通过 CLI 调用的网页搜索适配器，满足 `_search_cli.Backend` interface（`probe` / `search` + flags），分级见 `BackendRequirementLevel`。
_Avoid_: 搜索引擎、search provider 混称

**SearchBackendRegistry**:
深 Module，统一管理所有 Web 搜索类后端的注册、Result 归一与 `KeyProvider`，interface 仅 `register / get / search → Result[]`。定位为**程序化 seam**（测试与未来直接 import 的调用方）；Agent 消费的命令行表面走 `_search_cli`，两条路不得混用错误契约。
_Avoid_: backend manager、search service

**SearchResult**:
Registry 对外暴露的饱和小接口，含 `title / url / snippet / content / score / published_date / engine_meta`，缺失为 `None`，截断由 Registry 统一。
_Avoid_: raw response、organic_results 直出

**KeyProvider**:
Seam 处的 Key 解析 Adapter，优先级 `cli --api_key > env > .env`，供所有 Search Backend 共用。
_Avoid_: key loader、env helper 混称

**BackendSpec**:
声明式规格，描述单个 Search Backend 的 `name / env_key / flags / commands / timeout / circuit`，由 Registry 消费。
_Avoid_: backend config 泛称

**BackendRequirementLevel**:
Search Backend 的三档必要性分级，决定缺 key 时的编排行为：`required` 缺失则暂停并引导配置，`recommended` 缺失仅黄字提醒但允许匿名降级，`optional` 缺失静默跳过。
_Avoid_: 必选/可选二分、优先级混称

**Managed Command**:
由 `_search_cli` 骨架**全权接管执行流程**的一类 extra 命令（当前：Exa `answer` / `contents`、Tavily `extract`）。骨架负责密钥解析（经 `KeyProvider`，可读 `.env`）、SDK 缺失检查、client 构建、`invoke`（超时 / 重试 / 熔断）、错误 JSON 打印与退出码；命令体只声明「用 client 发起哪一次 SDK 调用」并返回待打印结果，失败时抛带 echo 标记（`query` / `url`）的错误。与未托管命令（如 SerpApi 的 `doc` / `engines` / `export`，各自保留 `(args)` 签名与错误契约）通过 `Command` 上的 opt-in 开关区分。
_Avoid_: 托管任务、wrapped command、managed handler 混称

**Report Validation**:
报告硬门禁集合，由 `validate_report.py` 强制（7 章节、引用闭环、双语、搜索源使用行等），`validate → errors[]` 为其 test surface；`verify_proof_integrity` 为其完整性复核半区——按与建据一致的原始字节重算 SHA-256 并比对 DONE 指纹，区分 `ReportTamperedError`（内容变）与 `ReportMissingError`（文件不可读）。
_Avoid_: report check 泛称

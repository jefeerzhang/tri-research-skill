# tri-research-skill

多源带引用深度研究 Skill 套件（主导代理 + 子代理 + 多搜索后端 + 报告验收）。

## Language

**Research Session**:
一次深度研究的生命周期容器，由 `state_machine.py` 的 `StateStore` 管理，经历 `STARTED → DONE`（可经 `add_dimensions` 进入 `EXTENDED`），以 `session_id` 标识。
_Avoid_: 任务、会话 id 混称

**Search Backend**:
一个可通过 CLI 调用的网页搜索适配器，满足 `_search_cli.Backend` interface（`probe` / `search` + flags），当前含 Exa / Tavily / SerpApi。
_Avoid_: 搜索引擎、search provider 混称

**SearchBackendRegistry**:
深 Module，统一管理所有 Web 搜索类后端的注册、Result 归一与 `KeyProvider`，interface 仅 `register / get / search → Result[]`。
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

**Report Validation**:
报告硬门禁集合，由 `validate_report.py` 强制（7 章节、引用闭环、双语、搜索源使用行等），`validate → errors[]` 为其 test surface。
_Avoid_: report check 泛称

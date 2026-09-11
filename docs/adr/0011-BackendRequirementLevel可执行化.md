# BackendRequirementLevel 可执行化

ADR-0001 立了 `required` / `recommended` / `optional` 三档，ADR-0006 / 0007 把 `required` 做成 `start` 硬门禁，但档位本身仍是文档加手抄常量：`required_backends._collect_gaps` 写死 Exa / SciVerse / SerpApi 的 env key、SDK 名与探活分支，Exa 另用 KeyProvider + `find_spec` 与 `Backend.client()` 并行判断「什么算就绪」。决定：档位成为描述符字段，Required 门禁改为遍历 `requirement=required` 的就绪描述符——Machine Web Backend 用 `Backend.requirement` + `Backend.readiness()`（装配判断与 `client()` 共用 `require_setup`：SDK → key；`start` 不构造 Exa client），SciVerse 用同列表上的 `SciVerseReadiness`，**不**注册进 `SearchBackendRegistry`（ADR-0006 边界不变）。Tavily 仍 `optional`；AnySearch `recommended` 本波保持文档-only。无 `ALLOW_DEGRADED` 逃逸。

## Considered Options

- **继续在 `require_required_backends` 里手抄三家常量**：被拒——加档 / 改档必须改 walker 正文，与「文档说 required、代码另写一份」同类漂移。
- **把 `requirement` 放进 `BackendSpec`**：被拒——Spec 是 Registry 身份（`name` / `backend`，ADR-0008 已删重复的 `env_key`）；档位再抄一份就能与 Backend 不同意。SciVerse 也不进 Registry。
- **把 SciVerse 塞进 Registry 当 Web Backend 再统一字段**：被拒——与 ADR-0006 相同理由：SciVerse 是学术 SDK 路径。
- **AnySearch `recommended` 本波也机器化（黄字提醒）**：被拒——要接外部 CLI/匿名额度探测，成本超过本波；语义仍以 CONTEXT / SKILL 为准。
- **（采用）`Backend.requirement` + `readiness()` + `SciVerseReadiness` 同一轮询列表**：改档只改字段；Exa 就绪与 `client()` 共用 `require_setup` 判断（start 不构造 SDK client）；SciVerse 留在列表外的 Registry。

## Consequences

- `BackendRequirementLevel`（`required` / `recommended` / `optional`）是可执行枚举，住在 `_search_cli`（与 `Backend` 同模块）。
- Exa：`requirement=required`，`readiness()` 走与 `client()` 同一套装配判断（`require_setup`：SDK 在场 → key 可解析），**不**在 `start` 时构造 SDK client（K+S，无 start 探活，ADR-0006）。SDK 与 key 同时缺时只报 SDK（与其余泳道同一顺序，ADR-0002 / 0008）。
- SerpApi：`requirement=required` 且 `start_probe=True`，`readiness()` = `client()` + `probe`（ADR-0007 语义不变）。
- Tavily：`requirement=optional`，已在同一列表上；升为 `required` 只需改字段，不必改 walker。
- SciVerse：`SciVerseReadiness` 做 K+S（KeyProvider + SDK import），挂在 `iter_readiness_descriptors()`；禁止 `REGISTRY.register`。
- `require_required_backends` 只遍历 `iter_required_descriptors()`，收集 gap、拼 guide；guide 文案来自各描述符的 `configure_hint` / `verify_cmd`。
- `runtime-adapters.md` 给出 WebBackend vs ExternalTool 扩展清单；合约测试钉住章节存在。
- 不在本 ADR 落地：AnySearch 机器黄字、ADR-0012 安装捆绑、architecture.json 重绘、打包成 wheel。
- 测试：原 `test_required_backends` 行为钉仍绿；新增「改 `requirement` 即改门禁成员」的数据驱动用例；无 `ALLOW_DEGRADED`。

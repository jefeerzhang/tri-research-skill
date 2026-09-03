# required（Exa / SciVerse）机器硬门禁

ADR-0001 将 Exa / SciVerse 定为 `required` 但刻意文档-only，约束力靠 Lead 纪律；实践中 SKILL「用户明确要求降级」与 README「必选未配置仍尝试无 API」仍能漏跑。决定：在 Research Session `start` 前对 Exa + SciVerse 做 K+S 机器检查（Key 可经 KeyProvider 解析且 SDK 可 import），失败抛 `StateError`、不建会话；无用户/env 逃逸开关。检查放在独立模块 `required_backends.py`，由 `StateStore.start_session` 调用——状态机只依赖该窄 seam，不把 SciVerse 塞进 `SearchBackendRegistry`，也不在每个 Search 调用散落检查。AnySearch `recommended` 匿名与检索中段优雅降级不动。

## Considered Options

- **继续文档-only**：被拒——逃逸口已证明会漏。
- **把 SciVerse 注册进 Registry 再统一 required 字段**：被拒——SciVerse 是学术 SDK 路径，不是 Web Search Backend，硬塞破坏 Registry 边界。
- **`start` 时活体 probe**：被拒——网络/代理抖动会误拦「未配置」；探活仍留在 SKILL 源检测步骤。
- **测试/CI 专用 `ALLOW_DEGRADED` env**：被拒——Agent 可设同一开关，等于恢复逃逸口；测试改 patch seam 或假 key + stub SDK。
- **（采用）独立门禁模块 + `start` 挂载 + 无逃逸**：一次拦死开跑，隔离性可接受。

## Consequences

- 未配置 Exa/SciVerse（或缺 SDK）时 `state_machine start` 直接 `ERROR:` + exit 1。
- SciVerse token：`KeyProvider`（env；若设 `SCIVERSE_HOME` 再读 `$SCIVERSE_HOME/.env`），不硬编码技能目录进 KeyProvider（ADR-0004）。
- Exa：沿用 `skills/tri-research/.env` 作为 `env_file`（与 Exa Backend 一致）。
- 文档须删除 Required 降级逃逸措辞；合约测试钉住。
- 测试：`tests/test_required_backends.py`；CLI 子进程经 `_test_helpers.required_backend_cli_env` 注入假 key + stub SDK。

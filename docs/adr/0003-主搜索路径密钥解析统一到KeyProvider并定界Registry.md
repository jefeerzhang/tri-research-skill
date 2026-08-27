# 主搜索路径密钥解析统一到 KeyProvider，Registry 定界为程序化 seam

`Backend.client()` 与 `_search_cli.check` 只读 `os.environ`，而 managed command（ADR-0002）与 SerpApi 的 `load_key` 经 `KeyProvider` 支持 `.env` 兜底——把 key 配在 `.env` 的用户会被 `check` 告知「未配置」（探活撒谎）、`search` 直接失败，而这些 key 实际可用。决定把 `_search_cli` 的密钥解析统一到 `KeyProvider`（新增 `_backend_api_key` seam，client / check / managed 三处共用），并删除全仓零调用的 `Registry.search_raw`。本 ADR 同时关闭 ADR-0002 遗留的「有意保留密钥来源不一致」。

## Considered Options

- **全量收编（CLI 内部改走 Registry）**：成功输出可保形，但「缺 key」错误形状会从 `{"error"}` 变为 `{"error", "query"}`、`--no-proxy check` 的行为也会改变——为一个当前尚无程序化消费方的 seam 冒输出契约漂移的险，YAGNI。
- **退役 Registry.search/batch_search/check**：这些方法有测试在钉（search 12 处、batch_search 3 处、check 1 处），删除等于推翻 v6.5.0 ticket #6 的 expand 方向；未来统一还需重造。
- **（采用）修复 + 划界**：① `client()` / `check()` 经 `_backend_api_key` 走 `KeyProvider`，探活与检索口径一致；② 删除零调用的 `search_raw`（git 历史保留，若将来 CLI 迁移到 Registry，可作为保形摆渡找回）；③ docstring / `CONTEXT.md` 写明分工：`_search_cli` = Agent 命令行表面，Registry = 程序化 seam，两条路不得混用错误契约。

## Consequences

- `.env` 兜底对 Exa / Tavily / SerpApi 的 `check` 与 `search` 全部生效；README 两处「密钥只从环境变量读取」改为「环境变量或本地 `.env`（已 gitignore）」。缺 key 时的错误 JSON 形状不变（`{"error": "<ENV> not set"}` / `{"available": false, ...}`）。
- **重开条件**：出现第二个程序化消费方（Lead Agent 直接 import `REGISTRY` 而非调 CLI）时，才值得做「CLI 内部走 Registry」的全量收编；届时以 `search_raw`（git 历史）为保形摆渡。
- 已知限制（本次未动）：`Registry.register` 原地修改共享 Backend 实例的 override，两条 seam 共享可变状态；出现跨 seam 干扰时再处理。
- 测试：`tests/test_backend_key_resolution.py` 钉住 client / check 的 KeyProvider 委托与错误形状。

# SerpApi 升为 required（Key + 轻量探活）并确立 Scholar 为间接能力

ADR-0006 把 Exa / SciVerse 定为 `required` 的 K+S 机器硬门禁（Key + SDK，均无 start 期探活），并把「start 时活体 probe」作为被拒选项之一（网络/代理抖动会误拦「未配置」）。本 ADR 在**不推翻 ADR-0006 分级语义**的前提下补充第三档 `required` SerpApi，并**仅对 SerpApi** 超集式地接受 start 期轻量探活——因为 SerpApi 的「可用」不只是 Key 存在，invalid/revoked key 只有发一次真实请求才拦得住。

## Context

- 人文社科的 Google Scholar 是重要发现通道，本仓库只能经 SerpApi 的 `google_scholar` engine 间接获得。
- 原 SerpApi 是 `optional`：缺 Key 静默跳过，Lead 未配置时学术发现腿常整段缺失；即便配置，编排也未把 SerpApi 与「社科须打 Scholar」写清。
- SciVerse 承担学术书目/语义面，OpenAlex 不在本次范围；不引入独立 OpenAlex Backend。

## Decision

1. **Tier**：SerpApi 从 `optional` → `required`（在 `BackendRequirementLevel`）。
2. **Gate shape（单一 seam）**：仍只扩 `require_required_backends`；`StateStore.start_session` 继续只调用它。SerpApi 检查 = **Key 可解析**（`KeyProvider`，`SERPAPI_KEY`，SerpApi Backend `env_file`）+ **轻量探活**（复用 `SerpApiBackend.probe`，`serpapi_cli.py check` 同一路径）。失败抛 `StateError`、不建会话。
3. **Exa / SciVerse 不变**：K+S，无 start 网络探活。本 ADR 是**对 ADR-0006 的窄例外**（仅 SerpApi），不是开启所有 required 探活。
4. **Scholar 是间接能力**：非独立 Backend，`Status 来源:` token 仍记 `SerpApi`（不改成 "Google Scholar"）。SKILL 仅约定：人文社科（HSS）主题 Lead 至少一轮 `--engine google_scholar`；STEM 主题不强制，避免烧配额。
5. **子代理不变**：仍用 AnySearch + SciVerse + Exa，无 SerpApi。
6. **OpenAlex**：out of scope；SciVerse 术语上不是 OpenAlex 代名词。
7. **测试**：默认套件不联网——`required_backend_cli_env` 注入 `SERPAPI_KEY` 并靠 PYTHONPATH 上的 stub `requests`（与 `exa_py` / `sciverse` stub 一致）让探活离线通过；探活成败在 gate seam 用 mock 覆盖。**无 `ALLOW_DEGRADED` 逃逸开关**。

## Consequences

- `state_machine start` 前三类依赖全部就绪才开跑：Exa / SciVerse（K+S）+ SerpApi（Key + 探活）。
- 未配 `SERPAPI_KEY` 或探活失败 → `ERROR:` + exit 1，错误文本点名 `SERPAPI_KEY`、申请链接（serpapi.com/dashboard）与验证命令（`serpapi_cli.py check`）。
- `Google Scholar` 只在 SKILL/README 以「SerpApi 间接能力」呈现；Evidence Ledger / `来源:` 词汇稳定为 `SerpApi`。
- 文档（SKILL / README / runtime-adapters / CONTEXT）档位表与引导同步；删除「SerpApi 可选 / 静默跳过」措辞。

## Considered Options

- **仍文档-only / optional**：被拒——逃逸口（静默跳过）已证明会漏 Scholar 腿。
- **把 SerpApi 塞进 SearchBackendRegistry 统一 required 字段**：被拒——SerpApi 已注册进 Registry，但这条门禁属于 required-backends 单 seam，不另起 SerpApi 专属 gate API。
- **start 期对 Exa / SciVerse 也做探活**：被拒——保持 ADR-0006 拒绝（网络/代理抖动误拦）；仅 SerpApi 特例。
- **`ALLOW_DEGRADED` env**：被拒——Agent 可设同一开关，等于恢复逃逸口；测试改 stub / patch seam。

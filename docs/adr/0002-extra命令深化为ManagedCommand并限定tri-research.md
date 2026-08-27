# extra 命令深化为 Managed Command 并有意限定 tri-research

`search_backends.py` 里 Exa `answer` / `contents` 与 Tavily `extract` 三个命令各自手抄约 20 行相同的 client bootstrap（清代理 → `KeyProvider.resolve` → 查 api_key → 查 sdk → `client_factory` → `invoke` → 错误 JSON + exit）。这是 `_search_cli` 早已为 `check` / `search` / `batch_search` 消灭过一轮、却在 extra `Command` 扩展点上重新滋生的重复。决定把这三条命令深化为 **Managed Command**：`Command` 增加 opt-in 开关，骨架统一接管密钥解析、SDK 检查、client 构建、`invoke`、错误打印与退出；命令体只声明「用 client 发起哪一次 SDK 调用」并返回结果。术语以 `CONTEXT.md` 的「Managed Command」为单一真源。

## Considered Options

- **全部 extra 命令（含 SerpApi）统一进骨架**：seam 最干净，但 SerpApi `export` 走 stderr + 多级退出码且要落 Markdown 文件，与 tri 三命令的 stdout-JSON 契约不同形，硬并会把两种错误契约搅进一个 seam，且改动跨 `tri-research` 与 `serpapi` 两个 skill——YAGNI，违背最小 blast radius（与 ADR-0001 的「文档-only 保持最小改动」一脉相承）。
- **新建 `DeepCommand` 类型**：tri 用新类、SerpApi 用旧类。引入两个近似概念，读者须先辨析其差别，增加认知噪音。
- **统一升级所有 `Command.run` 签名为托管**：会改动 SerpApi 的 `(args)` 签名，扩大 blast radius。
- **（采用）现有 `Command` 加 opt-in 开关，仅 tri 三命令拧到托管**：一处定义、SerpApi 因不碰开关而零改动、CLI 表面与输出逐字节向后兼容。密钥只走 `KeyProvider`（保留读 `.env`），并删除 `try: import KeyProvider / except ImportError` 的死回退分支（`search_backends.py` 顶层已无条件 import `_search_registry`，该分支永不触发）。

## Consequences

- **有意保留**一处不一致：Managed Command 经 `KeyProvider` 读 `.env`，而主搜索路径 `Backend.client()` 仍仅读 `os.environ`。本次不统一（属另一候选「reconcile `check` 密钥契约」的范围）。未来架构评审若提议「顺手把两条密钥路径统一 / 把 SerpApi 也纳入托管」，须先回到本 ADR 的划界理由，再决定是否重开。
- **不破坏测试**：`test_exa_search.py` / `test_tavily_search.py` 锁的是「无 SDK 时模块可加载 + `check` 吐 `{"available": false}`」，并未直接测三命令；骨架接管时须保持「先查 sdk 再建 client」的顺序，确保 SDK 为 `None` 时不崩、输出形状不变。
- 收益是 locality：代理 / 密钥 / SDK / 错误格式的漂移风险集中到骨架一处，命令体显著瘦身。

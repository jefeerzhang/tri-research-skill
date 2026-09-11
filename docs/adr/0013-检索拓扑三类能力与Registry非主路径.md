# 检索拓扑三类能力：Machine Backend / External Tool / Host

架构叙事把六源画成一条统一总线：`architecture.json` 把 AnySearch·SciVerse 标成「宿主 MCP」，边写成「MCP 工具调用」；CONTEXT / README 仍容易把 `SearchBackendRegistry` 读成 Lead 主路径。运行时并非如此。决定：文档化**三类检索能力**，并重绘架构真源。

- **Machine Backend**：仓内 `_search_cli.Backend`——Exa / Tavily / SerpApi。Agent 主路径走 CLI；`SearchBackendRegistry` 只是测试与 library import 的程序化 seam（ADR-0003），**不是** Lead 主路径，**不是** 六源总线。
- **External Tool**：仓外工具——AnySearch（CLI / public HTTP）与 SciVerse（Python SDK `AgentToolsClient`）。禁止 MCP 标签；SciVerse 不得注册进 Registry（ADR-0006 / ADR-0011）。
- **Host**：宿主内置 Runtime WebSearch。不等于 Tavily，不是 Search Backend。

调用矩阵（有子代理时）：Lead = Exa / SerpApi / Tavily / WebSearch；子代理 = AnySearch / SciVerse / Exa。无子代理时 Lead 直调全部可用源。Required 仍是 Exa + SciVerse + SerpApi（ADR-0006 / ADR-0007），本波不改 `required_backends`。

## Considered Options

- **维持「六源 Registry 总线」叙事**：被拒——Registry 只注册 Machine 三家；AnySearch / SciVerse / WebSearch 从不进 Registry。总线图会让 Agent 去 import `REGISTRY` 当主路径。
- **继续把 AnySearch·SciVerse 标成宿主 MCP**：被拒——SciVerse 唯一通道是 Python SDK（禁止 MCP）；AnySearch 是 CLI / HTTP。MCP 是错标签。
- **把 WebSearch 并进 External Tool（与 ADR-0010 台账通道同名）**：被拒——台账输入通道（非 Machine 的 `evidence.py add` 模板）与能力类是两条轴。能力类上 WebSearch 是 Host。
- **（采用）三类能力 + Registry 非主路径 + 按调用矩阵重绘**：CONTEXT / ADR / 架构图共读同一套词；合约测试钉住关键词与禁止 MCP 误标。

## Consequences

- `CONTEXT.md` 增加 Machine Backend / External Tool / Host 词条；`SearchBackendRegistry` 的 Avoid 写明非 Lead 主路径、非六源总线。
- `assets/tri-research-architecture.json` 拆开 AnySearch 与 SciVerse、补上 WebSearch，边按调用矩阵走，卡片点名 Exa + SciVerse + SerpApi 为 required。
- README 不再写「共享 CLI 骨架接六源」。
- 合约测试钉住架构 JSON / CONTEXT / ADR 关键词。
- ADR-0010 的台账通道不变：Machine 三家 `--session` 自动入账；AnySearch / SciVerse / WebSearch 仍用 `evidence.py add` 模板。
- 不在本 ADR 落地：ADR-0014（proof / exception / active-session）、打包（ADR-0015）、改 `required_backends` 行为。

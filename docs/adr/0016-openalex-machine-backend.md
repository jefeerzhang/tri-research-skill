# OpenAlex 接入为 optional Machine Backend（重开 ADR-0007§6）

ADR-0007 把独立 OpenAlex Backend 标成 out of scope，学术书目/语义面留给 SciVerse。实践中 OpenAlex 公开 `works` API 能补 DOI / OA / 年份 / 被引数，且匿名可搜，不该再藏在「不要把 SciVerse 改名」的禁令后面。决定：OpenAlex 成为第四家 **Machine Backend**（仓内 `_search_cli.Backend` + Registry），档位 `optional`，不抬高 `start` 硬门禁，无 `start_probe`。SciVerse 仍是 `required` External Tool，术语禁止混称。

点名名单随 R-A 原则扩到七源（演进 ADR-0009）：`USAGE_ROSTER` 增加 `OpenAlex`；未用可写 `0/跳过`。Machine `--session` 自动入账集合增加 OpenAlex（演进 ADR-0010）。检索拓扑 Machine 名单变为 Exa / Tavily / SerpApi / OpenAlex（演进 ADR-0013）。Delivery Unit 仍是 `tri-research` + `serpapi`（不新建兄弟 skill）。

## Considered Options

- **继续 defer（维持 ADR-0007§6）**：被拒——用户明确要求独立检索源；SciVerse token 与 Scholar 配额不能替代免费书目通道。
- **做成 External Tool / SciVerseReadiness**：被拒——实现住在仓内 HTTP adapter，不是仓外 SDK；硬塞破坏 ADR-0006 的 Registry 边界语义。
- **升为 `required` 或 `start_probe=True`**：被拒——匿名即可搜，抬高 `start` 无收益；探活例外仍仅 SerpApi（ADR-0007）。
- **新建 `skills/openalex` 兄弟 skill**：被拒——CLI 面与 Exa / Tavily 同形，Delivery Unit 不扩。
- **引入 `pyalex`**：被拒——标准库 `urllib` 足够。
- **（采用）optional Machine Backend + 七源点名 + 自动入账 + 新 ADR 显式重开 0007§6**。

## Consequences

- Agent 主路径：`scripts/openalex_search.py`（`search` / `batch_search` / `check`）；Registry 名 `openalex`。匿名可搜；可选 `OPENALEX_API_KEY`（Bearer）与 `OPENALEX_MAILTO`。只在本 Backend 覆盖 `require_setup` 以允许缺 key，Exa / Tavily / SerpApi 必填 key 语义不变。
- `iter_readiness_descriptors` 含 OpenAlex；`iter_required_descriptors` 仍为 Exa / SerpApi / SciVerse。
- 研究主路径 `--session` 写入 `seen.backend=OpenAlex`（与 `来源:` 词汇相同）。
- 调用矩阵：Lead 与子代理均可调用；SerpApi 仍仅 Lead。
- CONTEXT 增加 **OpenAlex** 词条；SciVerse Avoid 混称保留。
- 不重开 ADR-0006：SciVerse 仍是 `required` External Tool，**不进** Registry。
- 不在本 ADR 落地：semantic / rerank / 深分页 / 实体图谱 / DOI lookup / Managed Command / 升档。

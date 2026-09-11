# tri-research 与 serpapi 交付单元契约（D1）

SerpApi 已是 `required` Search Backend（ADR-0007：Key + 轻量探活，失败则 `state_machine start` 抛 `StateError`），实现却住在兄弟 skill `skills/serpapi/`，且 `serpapi_cli` 反向 import `tri-research/scripts/_search_cli`（ADR-0004 有意留下的路径耦合）。根 README 快速开始只写 `npx skills add … --skill tri-research`，serpapi SKILL 仍写「非默认 / 可回退其他搜索」。审计：静默单技能安装会被读成「足以开跑」，与硬门禁打架。用户锁定 **D1**。

决定：开跑一次 Research Session 的**最小安装集合**是 `tri-research` + `serpapi`（`research-subagent` 推荐，`citations` 可选）。只装 `tri-research` **不足以** `state_machine start`。路径耦合本波不根治，待 ADR-0015 共享 wheel。

## Considered Options

- **D2：把 SerpApi 代码并进 tri-research**：被拒——交付面一次拆掉独立 skill，爆炸半径远大于文档契约；本波 out of scope。
- **D3：把 SerpApi 降为 `recommended`**：被拒——等于重开 ADR-0007；用户已锁 D1。
- **本波落地 ADR-0015 共享 wheel**：被拒——解耦 import 路径是下一决策；本 ADR 只把「必须两 skill 同在」写成契约，不假装耦合已消失。
- **继续只写 `--skill tri-research`**：被拒——安装命令与 `required` 门禁两处真源，Agent / 用户会漏装 serpapi。
- **（采用）D1 伴生安装**：文档 + 合约测试钉住最小集合；Claude Code marketplace 用真实 `dependencies` 字段（`tri-research` → `serpapi`）；`npx skills add` **不**识别该字段，README 仍须两条安装命令。不发明 skills.sh 没有的安装器开关。

## Consequences

- 根 README / skill README 快速开始同时列出 `--skill tri-research` 与 `--skill serpapi`；删除「只装 tri-research 即就绪」的歧义。
- `.claude-plugin/marketplace.json`：`tri-research` 条目写 `dependencies: ["serpapi"]`（Claude Code 插件安装会解析伴生插件，见官方 plugin-dependencies）；描述不再称 serpapi 为「辅助」。不把 `research-subagent` 写进 `dependencies`（推荐，非开跑最小集）。
- `skills/serpapi/SKILL.md`：新增「当被 tri-research 引用时升为 required，不可回退」；Key 优先级与 KeyProvider 对齐（`cli > env > .env`）；删除「Default provider / fall back to other available search methods / 非默认」等与硬门禁冲突的句子。
- `CONTEXT.md` 增加 **Delivery Unit** 词条；术语以该处为单一真源。
- 合约测试钉住伴生安装措辞，并禁止冲突短语。
- **有意不动**：`required_backends.py` / Backend readiness（W2）；SerpApi 源码搬家（D2）；降档（D3）；共享 wheel（ADR-0015）；`architecture.json` 重绘。

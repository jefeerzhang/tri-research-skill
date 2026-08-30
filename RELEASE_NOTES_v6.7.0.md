# v6.7.0 — 2026-08-30

> 多源并行深度研究 Skill 套件；硬门禁、跨平台状态机、任意规模中英双补与可核验引用。

## 📌 一句话

聚焦两件事：(1) 把报告「交付」从纯 md 扩展为可核验的**书样 LaTeX/PDF**——`render_tex.py` 一键渲成 PDF，渲染时自动跳过 drawio 框架图，md 仍是唯一真源；同时内置 **TinyTeX**（轻量 LaTeX 引擎）安装引导，并把机制图/结构图内嵌进报告 md 写成推荐流程。(2) 把引用从「格式可查」升级为**证据可溯源**——Evidence Ledger 逐条对账硬门禁 + 台账指纹进 INTEGRITY。本版同时移除从未发布的 HTML 报告外壳，交付收敛为 md + pdf。

## ✨ Added

- **报告 LaTeX/PDF 渲染器**：新增 `scripts/render_tex.py`（内置 XeLaTeX + xeCJK 书样模板，5×8 英寸、思源/系统 CJK 字体可配、回退 Noto CJK，自包含不依赖外部模板仓库），把验收报告渲成书样 PDF。检测到 xelatex 自动编译（`TRI_RESEARCH_XELATEX` / `XELATEX` → TinyTeX 路径 → PATH），否则只产出 `.tex`；**渲染时自动跳过 drawio 框架图**（`![...]` 及 `*图：…*` 说明一并略去）。
- **TinyTeX 安装引导**：SKILL.md 新增轻量 LaTeX 引擎（PDF 编译）安装说明——Windows / macOS / Linux / R 四种安装方式、默认安装位置、`xelatex --version` 验证、脚本自动探测路径与 `tlmgr install` 缺包处理。
- **机制图/结构图嵌入（推荐）**：撰写阶段可用 `drawio-skill` 生成机制/结构图，以 base64 data-URI 内嵌进报告 md，使报告单文件自包含、无外部 PNG；中间产物（`.drawio` / `.png`）定稿后删除。
- **Evidence Ledger 引用溯源**：每会话一个 append-only 台账 `{session_id}.evidence.jsonl` + `scripts/evidence.py`（`add` / `list --summary` / `audit`），记录每波搜索见过的 URL 与出处、以及用户手动资料。
- **Evidence Audit 硬门禁**：`done` 在报告验证通过后逐条对账——每条引用 URL 经与 `validate_report` 同一套归一化后必须在台账命中（`user_provided` 同等资格），untraced 即失败并全量打印明细。
- **台账指纹进 INTEGRITY**：DONE proof 新增 `evidence_lines` + `evidence_sha256`，`check` 的 INTEGRITY 同时验报告与台账——DONE 后补行 / 篡改 / 删台账均如实报错。

## 🔁 Changed

- **移除 HTML 报告外壳**：删除 `scripts/render_report.py`、其测试与 ADR-0006，并从 SKILL.md / CONTEXT.md / README / report-format.md 清除引用；该功能属 Unreleased，从未进过发布通道。交付以报告 md + 书样 PDF 为准，md 仍是唯一真源。
- **StateError 下沉 `_common.py`**、**`start` 拒绝同名残留台账**、**行为收窄（schema v3 → v4）**：Evidence Ledger 落地时的收尾修正（承 Unreleased）。

## 🧪 Tests

- 总量 **218**（tri-research 208 + serpapi 10），自 v6.6.0 净增 36；CI 矩阵 Python 3.11–3.13 × ubuntu/windows，ruff (E/F) + markdownlint 全绿。

## ⚠️ Known Issues / Acknowledged Limitations

- 报告被合法移动/重命名后 `check` 报 `MISSING`，需重跑 `validate_report.py` + `done` 恢复；`revalidate` 快捷入口留待后续。
- `render_tex.py` 自动编译 PDF 需 xelatex（TinyTeX）；未装则只产出 `.tex`。
- serpapi → tri-research scripts 的 import 路径耦合与 `sys.path` 样板：待打包重构（ADR-0004 遗留）。
- `Registry.register` 对共享 Backend 实例原地 mutate override：两条 seam 共享可变状态，出现跨 seam 干扰时再处理（ADR-0003 已记）。

## 📥 Install / Upgrade

```bash
# If using the marketplace
claude plugin install jefeerzhang/tri-research-skill@v6.7.0
```

## 🔗 Full Diff & Changelog

- Full changelog: `skills/tri-research/CHANGELOG.md`
- 核心新增：书样 LaTeX/PDF 交付（`render_tex.py`）+ TinyTeX 引导 + Evidence Ledger 溯源对账
- 架构评审（v6.6.0 来源）: 加深候选见 `docs/adr/0002–0004`

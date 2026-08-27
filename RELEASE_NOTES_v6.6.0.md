# v6.6.0 — 2026-08-28

> 多源并行深度研究 Skill 套件；硬门禁、跨平台状态机、任意规模中英双补与可核验引用。

## 📌 一句话

聚焦三件事：(1) 把「完成后的完整性」从口头承诺升级为代码门禁——`check` 真复算报告 SHA-256；(2) 把「探活说什么」和「实际能不能用」对齐——密钥解析全线统一 KeyProvider，`.env` 用户不再被误报；(3) extra 命令深化为 **Managed Command**，漂移面收敛到骨架一处。本版源自一次完整的架构评审（5 个 deepening 候选全部落地，决策见 `docs/adr/0002–0004`）。

## 🐛 Fixed

- **探活与检索的密钥来源不一致**：`Backend.client()` / `_search_cli.check` 只读环境变量，`.env` 用户被 `check` 误报「未配置」而实际可用；统一经 `_backend_api_key` → KeyProvider 后三后端 `check` / `search` 全部支持 `.env`。顺带修正 KeyProvider serpapi 兜底路径多算一层 parent 的历史 bug（指向不存在的 `<root>/serpapi/.env`）。
- **`check` 的 `INTEGRITY:OK` 假闭环**：以前无论阶段、无论报告是否被改都打 OK。现在 DONE 后按与建据一致的原始字节口径重算 SHA-256：被改 `INTEGRITY:MISMATCH`、被移 `INTEGRITY:MISSING`，均退出码 1；`ERROR:` 前先 flush stdout，合并流下标记行顺序正确。
- **Tavily `--depth` 参数静默丢失**：CLI dest `depth` 与 API 形参 `search_depth` 未映射，`--depth advanced` 从未生效。
- **并发 `start` 偶发 traceback**：固定临时名互相踩踏 → PID 唯一临时名 + Windows 短退避重试（压测 0/360 失败）。

## 🔁 Changed

- **extra 命令深化为 Managed Command**：`Command` 新增 `managed` / `echo` opt-in 开关与 `run_managed_command` 骨架，统一接管代理清理、密钥解析、缺 SDK 检查、client 构建、超时/重试/熔断、错误 JSON 与退出码；Exa `answer` / `contents`、Tavily `extract` 三个命令体收敛为「一次 SDK 调用 + 结果整形」。CLI 表面与输出逐字节不变；SerpApi 三命令零改动（ADR-0002）。
- **`SearchBackendRegistry` 定界为程序化 seam**：删除全仓零调用的 `search_raw`；`_search_cli` = Agent 命令行表面，Registry = 程序化 seam，重开条件记入 ADR-0003。
- **后端自报 `.env` 位置（`Backend.env_file`）**：KeyProvider 删除全部硬编码候选，归零布局知识；新增后端只填自己的表。**行为收窄**：`SERPAPI_KEY` 写在 `skills/tri-research/.env` 不再被 serpapi 捞到（各后端只认自家 `.env`，ADR-0004）。
- **宿主助手去重**：proxy 清理元组收敛为 `_search_cli.clear_proxy_vars` 单一实现（源码闸门：全仓仅允许出现一次）；serpapi `load_key` 永不可达的 ImportError 回退分支及本地 `.env` 解析副本删除。`sys.path` 样板评估为不可合并（每份守护直接脚本调用场景），留待打包重构。

## ✨ Added

- **Managed Command 契约测试**：含成功/错误输出的**字节级**兼容断言（错误保持历史 ASCII 转义、`error` 先于 echo），与防止 glue 回流命令体的源码闸门。
- **完整性复核测试**：篡改 → `MISMATCH`、删除 → `MISSING`、未改 → `OK`，全部真子进程端到端。
- **密钥解析契约测试**：client / check 的 KeyProvider 委托、错误形状、三后端 `env_file` 目录归属精确断言、resolve 源码无技能名闸门。
- **宿主助手收敛闸门**：`tests/test_host_helpers.py` 目录穷举，proxy 元组全仓唯一。
- **搜索 CLI 超时 / 重试 / 熔断**（承 6.5.0）：`search` / `batch_search` 瞬时失败重试 + 单次超时 + 按后端熔断，`check` 只超时不重试。

## 🧪 Tests

- 总量 **182**（tri-research 172 + serpapi 10），本版净增 61；CI 矩阵 Python 3.11–3.13 × ubuntu/windows，ruff (E/F) + markdownlint 全绿。

## ⚠️ Known Issues / Acknowledged Limitations

- 报告被合法移动/重命名后 `check` 报 `MISSING`，需重跑 `validate_report.py` + `done` 恢复；`revalidate` 快捷入口留待后续。
- serpapi → tri-research scripts 的 import 路径耦合与 `sys.path` 样板：待打包重构（ADR-0004 遗留）。
- `Registry.register` 对共享 Backend 实例原地 mutate override：两条 seam 共享可变状态，出现跨 seam 干扰时再处理（ADR-0003 已记）。

## 📥 Install / Upgrade

```bash
# If using the marketplace
claude plugin install jefeerzhang/tri-research-skill@v6.6.0
```

## 🔗 Full Diff & Changelog

- Full changelog: `skills/tri-research/CHANGELOG.md`
- Architecture review（本版来源）: 5/5 deepening candidates landed, `docs/adr/0002–0004`
- This release commit: `401412a`（收口前最后一个内容提交）

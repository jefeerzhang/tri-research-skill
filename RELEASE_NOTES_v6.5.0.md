# v6.5.0 — 2026-08-24

> 多源并行深度研究 Skill 套件；硬门禁、跨平台状态机、任意规模中英双补与可核验引用。

## 📌 一句话

聚焦三件事：(1) 统一三搜索 CLI 契约骨架与共享能力；(2) 把"是否真用上了"从口头契约升级为代码约束；(3) 同步上游 AnySearch v3.1.0（CLI 直接调 public HTTP）。

## ✨ Added

- **跨文件版本对账动态化**：`tests/test_skill_contract.py` 的版本断言改为以 `SKILL.md` frontmatter 为单一真源动态对账，新增覆盖 `.claude-plugin/marketplace.json`、`citations/SKILL.md` 与 CHANGELOG 最新条目（修复 6.3.1 时 marketplace.json 漂移到 6.0.0 未被捕获的回归）。**发版不再需要改测试**。
- **金样例回归测试**：examples/ 下 4 份报告被 `validate_report.py` 端到端验证。
- **共享搜索 CLI 骨架**：`_search_cli.py` 内建 `timeout` / `retries` / `circuit-breaker`。
- **新样例**：`examples/DEEP_RESEARCH_双重差分法_2026-08-14.md`（30 条引用，含 LaTeX 数学附录）。

## 🔁 Changed

- **搜索后端统一到单一 module**：新增 `scripts/search_backends.py`，Exa / Tavily / SerpApi 三个 Backend 声明集中一处；`exa_search.py`、`tavily_search.py`、`serpapi_cli.py` 收敛为薄 CLI 入口。
- **SerpApi 接入共享 skeleton**：`search` / `check` / `batch_search` 复用 `_search_cli`；`doc` / `engines` / `export` 保留 extra commands；`--no-proxy`、`--json`、`--api_key` 保持原语义。
- **测试 fixture 去重**：`tests/_test_helpers.py` 提供共享 `make_valid_report` / `load_module`。
- **报告范式修正**：从"列信息"（X 报告称…）改为"凝练总结"（多源合起来说明什么洞察）。
- **子代理任务描述模板压缩**：去掉 MCP 引用，数据源改为 Python SDK。
- **`state_machine.py` 精简**：374 行 → 两步门禁（STARTED → DONE），代码量减半。

## 🐛 Fixed

- **AnySearch v3.1.0 同步**：CLI 迁到 `https://api.anysearch.com` public HTTP（Python `requests`，Node 内置 `https`）。
- **Proma 协作子会话**：实测不继承父会话 MCP 工具，从不可靠通道移除；`~/.claude/mcp.json` 不应再含 `sciverse` 段；`sciverse-mcp-server` npm 包不再需要安装。
- **验证器中文条目判定收紧**：CCTV 等孤立拉丁词嵌入中文条目不再算英文证据。
- **测试计数漂移**：README 中的 `35/35` 改为 `tests/test_count_drift.py` 自动统计+断言（消除文档漂移）。
- **SerpApi 文档漂移**：申请链接从控制台迁到 docs 统一鉴权章节。

## 📦 Dependencies

- AnySearch v3.1.0（CLI 直接调 public HTTP）
- sci
...[Truncated]...
────

- **`tools/test_count_drift.py`** 已纳入 CI（消除文档漂移）
- 跨平台文件锁三层降级：`fcntl` / `msvcrt` / 通用 pid+过期清理 fallback

## ⚠️ Known Issues / Acknowledged Limitations

- examples 中 `refactor/slim-down` 死分支引用已在 P0 修复中替换为 `master`（见 `fix_p0.patch`）
- "执行情况"段当前为字符串模式匹配约束，非结构化证据字段；后续版本计划迁入 state file

## 📥 Install / Upgrade

```bash
# If using the marketplace
claude plugin install jefeerzhang/tri-research-skill@v6.5.0
```

## 🔗 Full Diff & Changelog

- Full changelog: `skills/tri-research/CHANGELOG.md`
- This release commit: `4902809` (`docs(anysearch): AnySearch 接口同步到 v3.1.0`)

# tri-research-skill

多源带引用深度研究 Skill 套件（主导代理 + 子代理 + SerpApi 补强 + citations 可选复核）。

## Agent skills

### Issue tracker

Issues 存放在 GitHub Issues（jefeerzhang/tri-research-skill），全部通过 `gh` CLI 操作。See `docs/agents/issue-tracker.md`.

### Triage labels

五个 canonical triage roles，label 字符串与 role 名相同（needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix）。See `docs/agents/triage-labels.md`.

### Domain docs

Single-context：repo 根目录一个 `CONTEXT.md` + `docs/adr/`。See `docs/agents/domain.md`.

## 开发约定

- Python 脚本位于 `skills/*/scripts/`，标准库优先；测试用 `unittest`
- 运行全部测试：`python -m unittest discover -s skills/tri-research/tests` 与 `python -m unittest discover -s skills/serpapi/tests`
- CI 同时跑 ubuntu + windows（见 `.github/workflows/python-package.yml`），涉及文件读写时注意跨平台换行与路径
- 提交信息遵循中文 Conventional Commits（type 英文、scope/描述中文）

# tri-research-skill

## 触达分支（pointers）

- **Issue / PR 操作**：创建、查看、评论、打/去 label、关闭，一律经 `gh` CLI；PR 也是 triage 请求面、wayfinder 的 map/child/blocking 协议——全部在 `docs/agents/issue-tracker.md`
- **Triage 角色**：五个 canonical roles——needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix，label 字符串与 role 同名；映射表见 `docs/agents/triage-labels.md`
- **动代码前**：先读根目录 `CONTEXT.md`（领域词汇与 Avoid 词），需要决策背景再翻 `docs/adr/`；存在才读，缺失直接跳过。规则见 `docs/agents/domain.md`

## 开发约定

- Python 脚本在 `skills/*/scripts/`，标准库优先；测试用 `unittest`
- 全量测试（两侧都跑）：

  ```bash
  python -m unittest discover -s skills/tri-research/tests
  python -m unittest discover -s skills/serpapi/tests
  ```

- **测试数对账守门员**：`skills/tri-research/tests/test_count_drift.py` 静态统计两侧测试数（4 条断言），钉住 README / 示例 / CHANGELOG 里硬编码的数字。新增/删除测试后它变红 → 同步那些文档的数字
- **跨平台**：CI 同时跑 ubuntu + windows（`.github/workflows/python-package.yml`，Python 3.11–3.13 × 两系统，UTF-8 规避 Windows cp1252）；文件读写注意换行与路径
- **提交**：中文 Conventional Commits——type 英文小写、scope/描述中文（本地 commitlint + lint-staged 管格式）

**收尾**：改动落地前，全量测试通过、count-drift 守门员绿、commitlint 不红。

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
REPO_ROOT = ROOT.parents[1]


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.subagent = (ROOT.parent / "research-subagent" / "SKILL.md").read_text(encoding="utf-8")
        _root_readme_path = REPO_ROOT / "README.md"
        cls.root_readme = _root_readme_path.read_text(encoding="utf-8") if _root_readme_path.exists() else ""
        cls.test_prompts = (ROOT / "test-prompts.json").read_text(encoding="utf-8")

    def test_version_reconciliation(self) -> None:
        """跨文件版本对账:全部发布通道与 SKILL.md frontmatter 单一真源对齐。

        历史教训:6.3.1 时 marketplace.json 曾漂移到 6.0.0;此前本测试为
        硬编码版本字符串,且未覆盖 marketplace.json / citations SKILL.md。
        现改为从 frontmatter 动态读取,发版时无需改测试;[Unreleased] 期间
        CHANGELOG 最新「已发布」条目仍应等于 frontmatter 版本。
        """
        m = re.search(r'^version:\s*"([^"]+)"', self.skill, re.MULTILINE)
        self.assertIsNotNone(m, "tri-research SKILL.md frontmatter 缺少 version")
        v = m.group(1)

        self.assertIn(f'version: "{v}"', self.subagent, "research-subagent SKILL.md 版本漂移")
        citations = (ROOT.parent / "citations" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f'version: "{v}"', citations, "citations SKILL.md 版本漂移")
        self.assertIn(f"当前版本：`{v}`", self.readme, "skill README 当前版本漂移")
        if self.root_readme:
            self.assertIn(f"version-{v}", self.root_readme, "根 README 徽章版本漂移")
        self.assertIn(f'"version": "{v}"', self.test_prompts, "test-prompts.json 版本漂移")

        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(v, marketplace["metadata"]["version"], "marketplace.json metadata.version 漂移")

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        rel = re.search(r"^##\s+\[([^\]]+)\]\s+-\s+\d{4}-\d{2}-\d{2}\s*$", changelog, re.MULTILINE)
        self.assertIsNotNone(rel, "CHANGELOG 缺少已发布版本条目")
        self.assertEqual(v, rel.group(1), "CHANGELOG 最新发布版本与 frontmatter 不一致")

    def test_six_source_table_present(self) -> None:
        for name in ("AnySearch", "Tavily", "SciVerse", "Exa", "SerpApi", "WebSearch"):
            self.assertIn(name, self.skill)
            self.assertIn(name, self.readme)
            if self.root_readme:
                self.assertIn(name, self.root_readme)
        self.assertIn("六个搜索后端", self.skill)
        self.assertIn("六个搜索后端", self.readme)

    def test_skill_is_concise(self) -> None:
        self.assertLessEqual(len(self.skill.splitlines()), 450)

    def test_subagent_is_concise(self) -> None:
        self.assertLessEqual(len(self.subagent.splitlines()), 120)

    def test_citation_format_documented(self) -> None:
        # 硬门禁清单里的引用行字段锚点（模板本体在 references/report-format.md）
        self.assertIn("层级:", self.skill)
        self.assertIn("来源:", self.skill)

    def test_chinese_first(self) -> None:
        self.assertNotIn("## TL;DR", self.skill)
        self.assertNotIn("## Summary", self.skill)

    def test_source_allocation(self) -> None:
        self.assertIn("AnySearch", self.skill)
        self.assertIn("SciVerse", self.skill)
        self.assertIn("Exa", self.skill)
        self.assertIn("SerpApi", self.skill)
        self.assertIn("WebSearch", self.skill)

    def test_exa_is_required_tier_across_docs(self) -> None:
        """ADR-0001 把 Exa 提升为 required；各处文档表格/引导不得再标可选。

        合约测试此前只查六源名字（test_six_source_table_present /
        test_source_allocation），不查档位，于是 skill README / runtime-adapters
        把 Exa 悄悄留成「可选」也没人拦。
        """
        runtime_adapters = (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8")
        docs = (
            ("skill", self.skill),
            ("readme", self.readme),
            ("root_readme", self.root_readme),
            ("runtime_adapters", runtime_adapters),
        )
        for name, blob in docs:
            if not blob:
                continue
            # 任何点名 Exa 且带档位词的表格行，必须是必选/required，不得是可选/optional。
            for line in blob.splitlines():
                if "Exa" in line and "|" in line and any(t in line for t in ("必选", "可选", "required", "optional")):
                    self.assertTrue(
                        ("必选" in line or "required" in line) and not ("可选" in line or "optional" in line),
                        msg=f"{name}: Exa 档位漂移（应为必选/required）: {line}",
                    )
            self.assertNotIn("Exa 是可选", blob, msg=name)

    def test_skill_does_not_claim_env_only_keys(self) -> None:
        """SKILL 曾写「API key 只读环境变量」，但 KeyProvider 实为 cli > env > .env。

        实现（_search_registry.KeyProvider + Backend.env_file，ADR-0004）早就吃
        本地 `.env`；文档再说「只读环境变量」会误导用户以为 .env 不生效。
        """
        self.assertNotIn("只读环境变量", self.skill)
        self.assertIn("`.env`", self.skill)

    def test_anysearch_guide_has_real_validation_command(self) -> None:
        """首次使用引导表 AnySearch 的验证列曾是占位符「验证命令」，须给可运行命令。

        其他行（Exa/SciVerse/Tavily）都给了具体命令，AnySearch 行不能留占位符。
        """
        guide_row = next(
            ln for ln in self.skill.splitlines() if ln.startswith("| **AnySearch**") and "npx skills add" in ln
        )
        cells = [c.strip() for c in guide_row.split("|")]
        validation_cell = cells[3]  # ['', 源, 安装, 验证, 必要性, '']
        self.assertNotIn("验证命令", validation_cell)
        self.assertIn("`", validation_cell)

    def test_subagent_uses_only_allowed_sources(self) -> None:
        self.assertIn("AnySearch", self.subagent)
        self.assertIn("SciVerse", self.subagent)
        self.assertIn("Exa", self.subagent)
        self.assertNotIn("SerpApi", self.subagent)

    def test_lead_uses_anysearch_when_no_subagent(self) -> None:
        # Lead Agent should be able to use AnySearch directly
        self.assertIn("Lead Agent + 子代理", self.skill)
        # AnySearch must be mandatory for all agents
        self.assertIn("必选搜索源", self.skill)
        # Fallback chain must be documented
        self.assertIn("fallback", self.skill.lower())

    def test_search_execution_spec(self) -> None:
        # Search execution spec must be documented
        self.assertIn("搜索执行规范", self.skill)
        # Bilingual requirement - must be prominent (leading words only;
        # sentence-level wording is free to evolve)
        self.assertIn("中英双补", self.skill)
        self.assertIn("全源覆盖", self.skill)
        # Full source coverage per dimension; both AnySearch and SciVerse mandatory
        self.assertIn("必选搜索源", self.skill)
        # SciVerse must have a bilingual usage example
        self.assertIn("semantic_search", self.skill)

    def test_report_format_disclosed_to_reference(self) -> None:
        # 格式契约下放到 references/report-format.md；SKILL.md 保留 context pointer，
        # 七章节锚点改在 reference 上断言。
        self.assertIn("references/report-format.md", self.skill)
        reference = (ROOT / "references" / "report-format.md").read_text(encoding="utf-8")
        for section in (
            "## 概述",
            "## 已有事实",
            "## 主要文献观点",
            "## 主要矛盾与冲突点",
            "## 未来研究方向",
            "## 参考文献",
            "## 执行情况",
        ):
            self.assertIn(section, reference)
        self.assertIn("层级:", reference)
        self.assertIn("来源:", reference)

    def test_anysearch_3_compatible(self) -> None:
        self.assertIn("get_sub_domains", self.subagent)
        self.assertIn("runtime.conf", self.subagent)

    def test_sciverse_python_sdk_not_mcp(self) -> None:
        # v6.0.0 起 SciVerse 走 Python SDK 必选路径
        self.assertIn("SciVerse 调用规范", self.skill)
        self.assertIn("pip install sciverse", self.skill)
        self.assertIn("AgentToolsClient", self.skill)
        self.assertIn("SCIVERSE_API_TOKEN", self.skill)
        # 禁止项:不应包含 SciVerse 工具调用形式 (e.g. mcp__sciverse__semantic_search)
        self.assertNotIn("mcp__sciverse__semantic_search", self.skill)
        self.assertNotIn("mcp__sciverse__search_papers", self.skill)
        self.assertNotIn("mcp__sciverse__read_content", self.skill)
        # 必含 "Python SDK" 作为必选路径明示
        self.assertIn("Python SDK", self.skill)
        # 必含 "禁止" 的反例黑名单
        self.assertIn("禁止", self.skill)

    def test_state_machine_is_two_step(self) -> None:
        state_script = (ROOT / "scripts" / "state_machine.py").read_text(encoding="utf-8")
        self.assertIn("STARTED", state_script)
        self.assertIn("DONE", state_script)
        self.assertNotIn("record_dispatch", state_script)
        self.assertNotIn("record_result", state_script)

    def test_hard_gates_documented(self) -> None:
        # Soft policies must not be presented as the only completion criteria
        self.assertIn("硬门禁", self.skill)
        self.assertIn("推荐流程", self.skill)
        self.assertIn("代码不审计", self.skill)
        self.assertIn("报告级", self.skill)
        # validate_report scope must be explicit
        self.assertIn("validate_report.py", self.skill)
        self.assertIn("只做报告级", self.skill)

    def test_docs_do_not_promise_removed_ledger_apis(self) -> None:
        # v6 removed dispatch ledger from state_machine; docs/prompts must not require it
        for blob_name, blob in (
            ("skill", self.skill),
            ("readme", self.readme),
            ("root_readme", self.root_readme),
            ("test_prompts", self.test_prompts),
        ):
            self.assertNotIn("record_dispatch", blob, msg=blob_name)
            self.assertNotIn("record_result", blob, msg=blob_name)

    def test_tavily_listed_in_main_skill(self) -> None:
        # v6.3.1：Tavily 为六源之一，仅 Lead Agent；subagent 用 AnySearch+SciVerse+Exa
        self.assertIn("Tavily", self.skill)
        self.assertNotIn("Tavily", self.subagent)


if __name__ == "__main__":
    unittest.main()

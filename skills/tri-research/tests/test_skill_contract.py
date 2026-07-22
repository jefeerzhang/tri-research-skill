from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.subagent = (ROOT.parent / "research-subagent" / "SKILL.md").read_text(
            encoding="utf-8"
        )

    def test_skill_is_concise(self) -> None:
        self.assertLessEqual(len(self.skill.splitlines()), 400)

    def test_subagent_is_concise(self) -> None:
        self.assertLessEqual(len(self.subagent.splitlines()), 120)

    def test_report_format_documented(self) -> None:
        for section in ("## 概述", "## 已有事实", "## 主要文献观点", "## 主要矛盾与冲突点", "## 未来研究方向", "## 参考文献", "## 执行情况"):
            self.assertIn(section, self.skill)

    def test_citation_format_documented(self) -> None:
        self.assertIn("层级:", self.skill)
        self.assertIn("来源:", self.skill)

    def test_chinese_first(self) -> None:
        self.assertNotIn("## TL;DR", self.skill)
        self.assertNotIn("## Summary", self.skill)

    def test_source_allocation(self) -> None:
        self.assertIn("AnySearch", self.skill)
        self.assertIn("SciVerse", self.skill)
        self.assertIn("SerpApi", self.skill)
        self.assertIn("WebSearch", self.skill)

    def test_subagent_uses_only_allowed_sources(self) -> None:
        self.assertIn("AnySearch", self.subagent)
        self.assertIn("SciVerse", self.subagent)
        self.assertNotIn("SerpApi", self.subagent)

    def test_lead_uses_anysearch_when_no_subagent(self) -> None:
        # Lead Agent should be able to use AnySearch directly
        self.assertIn("Lead Agent + 子代理", self.skill)
        # AnySearch must be mandatory for all agents
        self.assertIn("必选搜索源", self.skill)
        # Fallback chain must be documented
        self.assertIn("fallback", self.skill.lower())
        self.assertIn("Node.js", self.skill)

    def test_search_execution_spec(self) -> None:
        # Search execution spec must be documented
        self.assertIn("搜索执行规范", self.skill)
        # Bilingual requirement - must be prominent
        self.assertIn("中英双补", self.skill)
        self.assertIn("禁止只搜英文不搜中文", self.skill)
        # Full source coverage per dimension
        self.assertIn("全源覆盖", self.skill)
        # Both AnySearch and SciVerse are mandatory
        self.assertIn("AnySearch 和 SciVerse 是必选", self.skill)
        # SciVerse must have bilingual example
        self.assertIn("semantic_search \"人工智能", self.skill)

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

    def test_tavily_listed_in_main_skill(self) -> None:
        # v6.0.0 起 Tavily 重新列为独立的第 5 后端（与 Runtime WebSearch 区分），
        # tri-research SKILL.md 必须提到 Tavily（用于子代理独立使用）；
        # 但 research-subagent SKILL.md 仍不应提 Tavily（subagent 用 AnySearch+SciVerse）
        self.assertIn("Tavily", self.skill)
        self.assertNotIn("Tavily", self.subagent)


if __name__ == "__main__":
    unittest.main()


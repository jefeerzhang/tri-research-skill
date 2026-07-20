from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
VERSION = "5.6.0"


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.prompts = json.loads((ROOT / "test-prompts.json").read_text(encoding="utf-8"))

    def test_versions_match(self) -> None:
        match = re.search(r"^version:\s*([^\s]+)", self.skill, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), VERSION)
        self.assertEqual(self.prompts["version"], VERSION)
        self.assertIn(f"当前版本：`{VERSION}`", self.readme)
        self.assertIn(f"## [{VERSION}]", self.changelog)

    def test_report_contract_requires_citations(self) -> None:
        self.assertNotIn("Do NOT include citations", self.skill)
        self.assertIn("参考文献", self.skill)
        self.assertIn("Found by", self.skill)

    def test_state_directory_is_separate_from_skill_home(self) -> None:
        self.assertIn("TRI_RESEARCH_STATE_DIR", self.skill)
        state_script = (ROOT / "scripts" / "state_machine.py").read_text(encoding="utf-8")
        self.assertNotIn('os.environ.get("TRI_RESEARCH_HOME")', state_script)

    def test_ai_labor_topic_is_an_end_to_end_case(self) -> None:
        cases = {item["id"]: item for item in self.prompts["prompts"]}
        case = cases["ai-labor-allocation"]
        self.assertEqual(case["topic"], "人工智能与劳动分配")
        self.assertGreaterEqual(case["expected_subagents"], 2)
        self.assertGreaterEqual(case["expected_sources_min"], 10)
        self.assertTrue(case["keywords_zh"])
        self.assertTrue(case["keywords_en"])

    def test_backend_count_is_unambiguous(self) -> None:
        self.assertIn("four optional external search backends", self.skill)
        self.assertIn("4 个可选外部后端 + 1 个运行时渠道", self.readme)

    def test_sciverse_has_portable_cli_fallback(self) -> None:
        self.assertIn("npx skills add https://sciverse.space", self.skill)
        self.assertIn("SCIVERSE_API_TOKEN", self.skill)
        self.assertIn("scripts/semantic_search.mjs", self.skill)
        self.assertIn("scripts/read_content.mjs", self.skill)
        self.assertIn("doc_id", self.prompts["prompts"][0]["expected_behavior"])

    def test_subagent_dispatch_is_failure_isolated(self) -> None:
        behavior = self.prompts["prompts"][0]["expected_behavior"]
        self.assertIn("allSettled", behavior)
        self.assertIn("不重新派发", behavior)
        self.assertIn("子代理启动后必须对允许的后端各执行一次本地预检", self.skill)
        self.assertIn("单源失败不得取消或丢弃其他源的成功结果", self.skill)


if __name__ == "__main__":
    unittest.main()

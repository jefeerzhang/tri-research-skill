"""金样例回归测试:examples/ 下所有示例报告必须通过当前 validate_report.py。

契约:验收器规则收紧时,示例报告要么同步修复、要么显式调整本文件的验收契约;
不允许「规则变了、样例悄悄不再合法」的漂移。
min_sources 取各样例发布时文档承诺的门槛(DID 样例在 skill README 承诺 18),
其余按状态机硬门禁下限 10。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from _test_helpers import load_module

SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_report.py"
EXAMPLES = Path(__file__).resolve().parents[3] / "examples"

MODULE = load_module(SCRIPT, "validate_report_golden")

# 文件名 → (min_sources, expected_topic);expected_topic 来自 H1 主题前缀
GOLDEN = {
    "DEEP_RESEARCH_AI与收入分配_2026-07-22_sciverse.md": (10, "人工智能与收入分配"),
    "DEEP_RESEARCH_AI与收入分配_2026-07-22_strict.md": (10, "人工智能与收入分配"),
    "DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md": (10, "人工智能与劳动分配"),
    "DEEP_RESEARCH_双重差分法_2026-08-14.md": (18, "双重差分法的最新理论进展与经验研究"),
    "DEEP_RESEARCH_气候风险与金融变革_2026-08-27.md": (10, "气候风险与金融领域变革"),
}


class GoldenExamplesTests(unittest.TestCase):
    def test_examples_dir_covers_all_reports(self) -> None:
        """GOLDEN 契约表必须与 examples/ 实际文件一一对应(新增样例须登记)。"""
        self.assertTrue(EXAMPLES.is_dir(), f"examples/ 目录不存在:{EXAMPLES}")
        on_disk = {p.name for p in EXAMPLES.glob("DEEP_RESEARCH_*.md")}
        self.assertEqual(
            set(GOLDEN),
            on_disk,
            "GOLDEN 契约表与 examples/ 不一致(新增/删除样例须同步本表)",
        )

    def test_golden_examples_pass_current_validator(self) -> None:
        for name, (min_sources, topic) in GOLDEN.items():
            with self.subTest(example=name):
                text = (EXAMPLES / name).read_text(encoding="utf-8")
                errors = MODULE.validate(text, min_sources, expected_topic=topic)
                self.assertEqual(
                    [],
                    errors,
                    f"金样例 {name} 未通过当前验收器(min_sources={min_sources}):\n" + "\n".join(errors),
                )


if __name__ == "__main__":
    unittest.main()

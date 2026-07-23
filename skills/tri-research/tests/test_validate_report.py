from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_report.py"
SPEC = importlib.util.spec_from_file_location("validate_report", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def valid_report() -> str:
    return """# 人工智能与劳动分配

## 概述
中文结论 with international evidence[1]。另一项机制见来源[2]。

## 已有事实
事实一[1]。事实二[2]。

## 主要文献观点
观点一[1]。观点二[2]。

## 主要矛盾与冲突点
矛盾一。

## 未来研究方向
方向一。

## 参考文献
[1] Organization — English source — https://publisher-one.org/one — 2025 — 层级: 1 — 来源: AnySearch
[2] 作者 — 中文来源 — https://publisher-two.cn/two — 2024 — 层级: 2 — 来源: AnySearch

## 执行情况

| 项目 | 说明 |
|------|------|
| 执行流程 | 预检 → 搜索 → 综合 → 验证 |
| 子代理派发 | 否 |
| 搜索源使用 | AnySearch: 2条 |
| 耗时 | 3.0 分钟 |
| 报告位置 | ~/tri-research-reports/report.md |
"""


class ReportValidatorTests(unittest.TestCase):
    def test_accepts_valid_report(self) -> None:
        self.assertEqual(
            MODULE.validate(valid_report(), 2, expected_topic="人工智能与劳动分配"),
            [],
        )

    def test_rejects_missing_sections(self) -> None:
        report = "# 标题\n\n无内容\n"
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("概述" in error for error in errors))
        self.assertTrue(any("已有事实" in error for error in errors))
        self.assertTrue(any("参考文献" in error for error in errors))

    def test_rejects_missing_and_broken_citations(self) -> None:
        report = (
            valid_report()
            .replace("[2] 作者", "[3] 作者")
            .replace("https://publisher-one.org/one", "missing-url")
        )
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("不连续" in error for error in errors))
        self.assertTrue(any("URL" in error for error in errors))

    def test_rejects_duplicate_reference_urls(self) -> None:
        report = valid_report().replace(
            "https://publisher-two.cn/two", "https://publisher-one.org/one"
        )
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("URL 重复" in error for error in errors))

    def test_rejects_placeholder_urls(self) -> None:
        for invalid_url in (
            "https://example.org/source",
            "http://localhost/source",
            "http://127.0.0.1/source",
        ):
            with self.subTest(url=invalid_url):
                report = valid_report().replace(
                    "https://publisher-one.org/one", invalid_url
                )
                errors = MODULE.validate(report, 2)
                self.assertTrue(any("URL 无效" in error for error in errors))

    def test_rejects_report_for_different_topic(self) -> None:
        errors = MODULE.validate(valid_report(), 2, expected_topic="量子芯片供应链")
        self.assertTrue(any("主题" in error for error in errors))

    def test_language_coverage(self) -> None:
        # Replace entire second reference with all-English entry
        report = valid_report().replace(
            "[2] 作者 — 中文来源 — https://publisher-two.cn/two — 2024 — 层级: 2 — 来源: AnySearch",
            "[2] Author — English — https://publisher-two.cn/two — 2024 — level: 2 — via: AnySearch"
        )
        errors = MODULE.validate(report, 2)
        # Should contain Chinese language missing error (other errors like tier/source format are expected too)
        self.assertTrue(any("缺少中文" in error for error in errors))

    def test_rejects_missing_tier(self) -> None:
        report = valid_report().replace("层级: 1", "无层级")
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("层级" in error for error in errors))

    def test_rejects_missing_source_tool(self) -> None:
        report = valid_report().replace("来源: AnySearch", "无来源")
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("来源工具" in error for error in errors))

    def test_rejects_duplicate_reference_numbers(self) -> None:
        report = valid_report().replace(
            "[2] 作者 — 中文来源 — https://publisher-two.cn/two — 2024 — 层级: 2 — 来源: AnySearch",
            "[1] Dup — duplicate number — https://publisher-two.cn/two — 2024 — 层级: 2 — 来源: AnySearch",
        )
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("重复" in e and "编号" in e for e in errors))

    def test_body_line_starting_with_bracket_number_is_not_a_reference(self) -> None:
        report = valid_report().replace(
            "事实一[1]。事实二[2]。",
            "事实一[1]。事实二[2]。\n[9] 注：这是正文里的编号行，不是参考文献条目。",
        )
        errors = MODULE.validate(report, 2)
        # 正文行不能变成幽灵参考文献条目（缺 URL/层级/来源、编号不连续）
        self.assertFalse(any("参考文献 [9]" in e for e in errors))
        self.assertFalse(any("不连续" in e for e in errors))
        # 但 [9] 仍按引用契约算行内引用，无对应条目必须报错
        self.assertTrue(any("无对应参考文献" in e and "[9]" in e for e in errors))

    def test_code_block_indexing_is_not_a_citation(self) -> None:
        report = valid_report().replace(
            "矛盾一。",
            "矛盾一。\n\n```python\nfirst = arr[0]\nsecond = arr[1]\n```\n",
        )
        errors = MODULE.validate(report, 2)
        self.assertFalse(any("[0]" in e for e in errors))

    def test_strip_url_punctuation_keeps_balanced_parens(self) -> None:
        self.assertEqual(
            MODULE._strip_url_punctuation("https://en.wikipedia.org/wiki/AI_(disambiguation)"),
            "https://en.wikipedia.org/wiki/AI_(disambiguation)",
        )
        self.assertEqual(
            MODULE._strip_url_punctuation("https://en.wikipedia.org/wiki/AI_(disambiguation)."),
            "https://en.wikipedia.org/wiki/AI_(disambiguation)",
        )
        self.assertEqual(
            MODULE._strip_url_punctuation("https://example.com/page)."),
            "https://example.com/page",
        )

    def test_report_with_utf8_bom_validates(self) -> None:
        errors = MODULE.validate(
            "\ufeff" + valid_report(), 2, expected_topic="人工智能与劳动分配"
        )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

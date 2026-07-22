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


if __name__ == "__main__":
    unittest.main()

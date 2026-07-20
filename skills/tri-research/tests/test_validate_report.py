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

## TL;DR
中文结论 with international evidence[1]。另一项机制见来源[2]。

## 搜索与降级状态
AnySearch: available; Tavily: quota_exhausted; SciVerse: unavailable.

## 参考文献
[1] Organization — English source — https://publisher-one.org/one — 2025 — Tier: 1 — Found by: AnySearch
[2] 作者 — 中文来源 — https://publisher-two.cn/two — 2024 — Tier: 2 — Found by: AnySearch
"""


class ReportValidatorTests(unittest.TestCase):
    def test_accepts_valid_report(self) -> None:
        self.assertEqual(
            MODULE.validate(valid_report(), 2, expected_topic="人工智能与劳动分配"),
            [],
        )

    def test_rejects_missing_and_broken_citations(self) -> None:
        report = (
            valid_report()
            .replace("[2] 作者", "[3] 作者")
            .replace("https://publisher-one.org/one", "missing-url")
        )
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("not consecutive" in error for error in errors))
        self.assertTrue(any("no URL" in error for error in errors))
        self.assertTrue(any("no reference entries" in error for error in errors))

    def test_rejects_duplicate_reference_urls(self) -> None:
        report = valid_report().replace(
            "https://publisher-two.cn/two", "https://publisher-one.org/one"
        )
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("URLs are not unique" in error for error in errors))
        self.assertTrue(any("unique reference URLs" in error for error in errors))

    def test_rejects_query_and_fragment_url_variants(self) -> None:
        report = valid_report().replace(
            "https://publisher-two.cn/two",
            "https://publisher-one.org/one?utm_source=test#abstract",
        )
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("URLs are not unique" in error for error in errors))

    def test_preserves_meaningful_query_identifiers(self) -> None:
        report = (
            valid_report()
            .replace(
                "https://publisher-one.org/one",
                "https://journal-publisher.org/article?id=one",
            )
            .replace(
                "https://publisher-two.cn/two",
                "https://journal-publisher.org/article?id=two",
            )
        )
        self.assertEqual(MODULE.validate(report, 2), [])

    def test_rejects_placeholder_and_nonpublic_urls(self) -> None:
        for invalid_url in (
            "https://example.org/source",
            "http://localhost/source",
            "http://127.0.0.1/source",
            "https://user:password@publisher-one.org/one",
        ):
            with self.subTest(url=invalid_url):
                report = valid_report().replace(
                    "https://publisher-one.org/one", invalid_url
                )
                errors = MODULE.validate(report, 2)
                self.assertTrue(
                    any("invalid http/https URL" in error for error in errors)
                )

    def test_rejects_report_for_a_different_topic(self) -> None:
        errors = MODULE.validate(valid_report(), 2, expected_topic="量子芯片供应链")
        self.assertTrue(any("confirmed topic" in error for error in errors))

    def test_language_coverage_must_come_from_references(self) -> None:
        report = valid_report().replace("作者 — 中文来源", "Author — English source")
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("Chinese-language reference" in error for error in errors))

    def test_channel_status_does_not_scan_later_sections(self) -> None:
        report = (
            valid_report()
            .replace(
                "AnySearch: available; Tavily: quota_exhausted; SciVerse: unavailable.",
                "本节没有规范化状态。",
            )
            .replace("## 参考文献", "## 参考文献\navailable")
        )
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("normalized channel status" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

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
[1] Organization — English source — https://example.com/one — 2025 — Tier: 1 — Found by: AnySearch
[2] 作者 — 中文来源 — https://example.cn/two — 2024 — Tier: 2 — Found by: AnySearch
"""


class ReportValidatorTests(unittest.TestCase):
    def test_accepts_valid_report(self) -> None:
        self.assertEqual(MODULE.validate(valid_report(), 2), [])

    def test_rejects_missing_and_broken_citations(self) -> None:
        report = valid_report().replace("[2] 作者", "[3] 作者").replace(
            "https://example.com/one", "missing-url"
        )
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("not consecutive" in error for error in errors))
        self.assertTrue(any("no URL" in error for error in errors))
        self.assertTrue(any("no reference entries" in error for error in errors))

    def test_rejects_duplicate_reference_urls(self) -> None:
        report = valid_report().replace("https://example.cn/two", "https://example.com/one")
        errors = MODULE.validate(report, 2)
        self.assertTrue(any("URLs are not unique" in error for error in errors))
        self.assertTrue(any("unique reference URLs" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

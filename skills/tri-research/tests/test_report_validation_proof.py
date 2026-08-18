"""Direct unit tests for the consolidated Report Validation module.

This pins the path-level proof lifecycle that used to be split between
state_machine.py and validate_report.py: read report -> validate text ->
build report_validation proof -> assert proof completeness.
"""
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from _test_helpers import make_valid_report

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"


def _load_validate_report():
    spec = importlib.util.spec_from_file_location(
        "validate_report_proof_test", str(SCRIPTS_DIR / "validate_report.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ReportValidationProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.vr = _load_validate_report()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_validate_and_build_proof_returns_complete_proof(self) -> None:
        report = self.tmp_path / "report.md"
        make_valid_report(report)
        proof = self.vr.validate_and_build_proof(report, 10, expected_topic="人工智能与劳动分配")
        self.assertEqual(proof["min_sources"], 10)
        self.assertEqual(proof["topic"], "人工智能与劳动分配")
        self.assertEqual(proof["path"], str(report.resolve()))
        expected_sha = hashlib.sha256(report.read_bytes()).hexdigest()
        self.assertEqual(proof["sha256"], expected_sha)
        self.assertIn("validated_at", proof)

    def test_validate_and_build_proof_rejects_missing_report(self) -> None:
        with self.assertRaises(self.vr.ReportValidationError):
            self.vr.validate_and_build_proof(self.tmp_path / "missing.md", 10, expected_topic="人工智能与劳动分配")

    def test_validate_and_build_proof_rejects_invalid_report(self) -> None:
        report = self.tmp_path / "bad.md"
        report.write_text("# 错误\n\n无内容\n", encoding="utf-8")
        with self.assertRaises(self.vr.ReportValidationError) as ctx:
            self.vr.validate_and_build_proof(report, 10, expected_topic="人工智能与劳动分配")
        self.assertIn("validation failed", str(ctx.exception))

    def test_require_complete_proof_accepts_full_proof(self) -> None:
        proof = {"path": "/tmp/report.md", "sha256": "abc", "min_sources": 10}
        self.vr.require_complete_proof(proof, "s1")

    def test_require_complete_proof_rejects_missing_proof(self) -> None:
        with self.assertRaises(self.vr.ReportValidationError) as ctx:
            self.vr.require_complete_proof(None, "s1")
        self.assertIn("missing", str(ctx.exception))

    def test_require_complete_proof_rejects_incomplete_proof(self) -> None:
        with self.assertRaises(self.vr.ReportValidationError) as ctx:
            self.vr.require_complete_proof({"path": "/tmp/report.md"}, "s1")
        self.assertIn("incomplete", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

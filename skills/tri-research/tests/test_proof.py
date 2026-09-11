"""Deep-module tests for the consolidated DONE ``report_validation`` proof.

Previously the proof lifecycle was split three ways: the report half in
``validate_report``, the ledger half in ``evidence``, and the merge/verify
orchestration in ``state_machine``. This suite pins a single ``proof``
module that owns the whole contract — build both halves, assert the full
schema, verify both halves — so proof knowledge stops leaking across
module boundaries.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _test_helpers import load_module, make_valid_report, patch_required_backends, register_report_evidence

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"


class ProofModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_path = Path(self.tmp.name)
        self.state_dir = self.tmp_path / "state"
        self.sm = load_module(SCRIPTS_DIR / "state_machine.py", "proof_test_sm")
        self.evidence = load_module(SCRIPTS_DIR / "evidence.py", "proof_test_evidence")
        self.proof = load_module(SCRIPTS_DIR / "proof.py", "proof_test_module")
        self.store = self.sm.StateStore(self.state_dir)
        self._backend_patch = patch_required_backends(self.sm)
        self._backend_patch.start()
        self.addCleanup(self._backend_patch.stop)
        self.store.start_session("s1")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _session(self) -> str:
        return "s1"

    def _report(self, name: str = "report.md") -> Path:
        report = self.tmp_path / name
        make_valid_report(report)
        register_report_evidence(self.state_dir, self._session(), report)
        return report

    def test_build_proof_merges_both_halves_into_complete_schema(self) -> None:
        report = self._report()
        proof = self.proof.build_proof(self.store, self._session(), report, 10, expected_topic="人工智能与劳动分配")
        # The report half ...
        self.assertEqual(proof["path"], str(report.resolve()))
        self.assertEqual(proof["min_sources"], 10)
        self.assertEqual(proof["topic"], "人工智能与劳动分配")
        self.assertIn("sha256", proof)
        self.assertIn("validated_at", proof)
        # ... and the ledger half both land in one dict (schema v4).
        self.assertIn("evidence_lines", proof)
        self.assertIn("evidence_sha256", proof)

    def test_require_complete_accepts_full_proof(self) -> None:
        report = self._report()
        proof = self.proof.build_proof(self.store, self._session(), report, 10, expected_topic="人工智能与劳动分配")
        self.proof.require_complete(proof, self._session())  # must not raise

    def test_require_complete_rejects_missing_proof(self) -> None:
        with self.assertRaises(self.proof.ProofError):
            self.proof.require_complete(None, "s1")

    def test_require_complete_rejects_partial_proof(self) -> None:
        with self.assertRaises(self.proof.ProofError):
            self.proof.require_complete({"path": "/tmp/x.md", "sha256": "abc"}, "s1")

    def test_verify_integrity_clean_returns_ok(self) -> None:
        report = self._report()
        proof = self.proof.build_proof(self.store, self._session(), report, 10, expected_topic="人工智能与劳动分配")
        self.assertEqual(self.proof.verify_integrity(proof, self.store, self._session()), "OK")

    def test_verify_integrity_detects_tampered_report(self) -> None:
        report = self._report()
        proof = self.proof.build_proof(self.store, self._session(), report, 10, expected_topic="人工智能与劳动分配")
        report.write_bytes(report.read_bytes() + "\n偷偷改一段\n".encode("utf-8"))
        with self.assertRaises(self.proof.ProofTamperedError):
            self.proof.verify_integrity(proof, self.store, self._session())

    def test_verify_integrity_detects_missing_report(self) -> None:
        report = self._report()
        proof = self.proof.build_proof(self.store, self._session(), report, 10, expected_topic="人工智能与劳动分配")
        report.unlink()
        with self.assertRaises(self.proof.ProofMissingError):
            self.proof.verify_integrity(proof, self.store, self._session())

    def test_verify_integrity_detects_tampered_ledger(self) -> None:
        report = self._report()
        proof = self.proof.build_proof(self.store, self._session(), report, 10, expected_topic="人工智能与劳动分配")
        ledger = self.evidence.evidence_path(self.store, self._session())
        with ledger.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write('{"kind":"seen","ts":"2026-01-01T00:00+00:00","backend":"x","query":"q","url":"https://late.example/1"}\n')
        with self.assertRaises(self.proof.ProofTamperedError):
            self.proof.verify_integrity(proof, self.store, self._session())

    def test_verify_integrity_detects_missing_ledger(self) -> None:
        report = self._report()
        proof = self.proof.build_proof(self.store, self._session(), report, 10, expected_topic="人工智能与劳动分配")
        self.evidence.evidence_path(self.store, self._session()).unlink()
        with self.assertRaises(self.proof.ProofMissingError):
            self.proof.verify_integrity(proof, self.store, self._session())

    def test_ledger_errors_are_evidence_errors_not_report_validation(self) -> None:
        """ADR-0014 / P1-6：台账指纹失败不得挂在 ReportValidationError 下。"""
        for name in ("LedgerIntegrityError", "LedgerMissingError", "LedgerTamperedError"):
            cls = getattr(self.evidence, name)
            self.assertTrue(
                issubclass(cls, self.evidence.EvidenceError),
                f"{name} must hang under EvidenceError",
            )
            self.assertFalse(
                any(base.__name__ == "ReportValidationError" for base in cls.__mro__),
                f"{name} must not inherit ReportValidationError",
            )

    def test_build_proof_without_audit_skips_traceability_gate(self) -> None:
        report = self.tmp_path / "no-audit.md"
        make_valid_report(report)
        proof = self.proof.build_proof(
            self.store,
            self._session(),
            report,
            10,
            expected_topic="人工智能与劳动分配",
            audit=False,
        )
        self.assertIn("sha256", proof)
        self.assertIn("evidence_sha256", proof)

    def test_build_proof_with_audit_rejects_untraced_references(self) -> None:
        report = self.tmp_path / "need-audit.md"
        make_valid_report(report)
        with self.assertRaises(Exception) as ctx:
            self.proof.build_proof(
                self.store,
                self._session(),
                report,
                10,
                expected_topic="人工智能与劳动分配",
                audit=True,
            )
        # Dual-load: catch by name, not the separately loaded evidence copy.
        self.assertEqual(type(ctx.exception).__name__, "EvidenceAuditFailed")

    def test_build_proof_with_audit_passes_when_ledger_covers_report(self) -> None:
        report = self._report()
        proof = self.proof.build_proof(
            self.store,
            self._session(),
            report,
            10,
            expected_topic="人工智能与劳动分配",
            audit=True,
        )
        self.assertIn("evidence_sha256", proof)
        self.assertGreater(proof["evidence_lines"], 0)


class DoneFacadeSourceTests(unittest.TestCase):
    """ADR-0014 / P1-7：complete() 只调门面，不散落第二次报告解析。"""

    def test_complete_calls_build_proof_with_audit_and_not_audit_report(self) -> None:
        source = (SCRIPTS_DIR / "state_machine.py").read_text(encoding="utf-8")
        start = source.index("    def complete(")
        end = source.index("    def resolve_session(")
        body = source[start:end]
        self.assertIn("build_proof(", body)
        self.assertIn("audit=True", body)
        self.assertNotIn("audit_report(", body)
        self.assertNotIn("validate_and_build_proof(", body)


if __name__ == "__main__":
    unittest.main()

"""Evidence Ledger CLI 契约测试：登记、翻阅、容错与封账。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _test_helpers import make_valid_report, register_report_evidence, report_reference_urls

SCRIPT = Path(__file__).parents[1] / "scripts" / "evidence.py"
STATE_MACHINE = Path(__file__).parents[1] / "scripts" / "state_machine.py"


class EvidenceCliHarness:
    """Shared evidence-CLI helpers, mixed into the TestCases below."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name) / "state"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_state_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
        command = [sys.executable, str(STATE_MACHINE), "--state-dir", str(self.state_dir), *args]
        result = subprocess.run(command, capture_output=True, text=True)
        if ok and result.returncode != 0:
            self.fail(f"state_machine failed: {command}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

    def run_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
        command = [sys.executable, str(SCRIPT), "--state-dir", str(self.state_dir), *args]
        result = subprocess.run(command, capture_output=True, text=True)
        if ok and result.returncode != 0:
            self.fail(f"failed: {command}\nstdout={result.stdout}\nstderr={result.stderr}")
        if not ok and result.returncode == 0:
            self.fail(f"unexpectedly succeeded: {command}\nstdout={result.stdout}")
        return result

    def start_session(self, session: str) -> None:
        self.run_state_cli("--session", session, "start")

    def list_records(self, session: str, *extra: str) -> list[dict]:
        result = self.run_cli("--session", session, "list", *extra)
        lines = [line for line in result.stdout.splitlines() if not line.startswith("SESSION:")]
        return [json.loads(line) for line in lines]

    def ledger_path(self, session: str) -> Path:
        return self.state_dir / f"{session}.evidence.jsonl"

    def drive_to_done(self, session: str) -> Path:
        """start -> set_params -> (register evidence) -> done --report."""
        self.start_session(session)
        params = json.dumps(
            {
                "topic": "人工智能与劳动分配",
                "min_sources": 10,
                "keywords_zh": ["人工智能"],
                "keywords_en": ["artificial intelligence"],
            },
            ensure_ascii=False,
        )
        self.run_state_cli("--session", session, "set_params", params)
        report = Path(self.temp_dir.name) / f"{session}.md"
        make_valid_report(report)
        register_report_evidence(self.state_dir, session, report)
        self.run_state_cli("--session", session, "done", "--report", str(report))
        return report


class EvidenceAddTests(EvidenceCliHarness, unittest.TestCase):
    def test_add_batch_seen_records(self) -> None:
        self.start_session("add-batch")
        result = self.run_cli(
            "--session",
            "add-batch",
            "add",
            "--backend",
            "exa",
            "--query",
            "AI 就业 影响",
            "--title",
            "研究：AI 与就业",
            "--url",
            "https://a.example.cn/1",
            "--url",
            "https://b.example.org/2",
        )
        self.assertIn("OK:Recorded 2 evidence record(s)", result.stdout)
        self.assertIn(f"FILE:{self.ledger_path('add-batch')}", result.stdout)
        records = self.list_records("add-batch")
        self.assertEqual(len(records), 2)
        for record, url in zip(records, ["https://a.example.cn/1", "https://b.example.org/2"], strict=True):
            self.assertEqual(record["kind"], "seen")
            self.assertEqual(record["backend"], "exa")
            self.assertEqual(record["query"], "AI 就业 影响")
            self.assertEqual(record["url"], url)
            self.assertEqual(record["title"], "研究：AI 与就业")
            self.assertIn("ts", record)

    def test_add_user_provided_record(self) -> None:
        self.start_session("user-provided")
        self.run_cli(
            "--session",
            "user-provided",
            "add",
            "--user-provided",
            "--url",
            "https://gov.cn/report.pdf",
            "--note",
            "用户给的行业年报",
        )
        records = self.list_records("user-provided")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "user_provided")
        self.assertEqual(records[0]["url"], "https://gov.cn/report.pdf")
        self.assertEqual(records[0]["note"], "用户给的行业年报")
        self.assertNotIn("backend", records[0])

    def test_seen_requires_backend_and_query(self) -> None:
        self.start_session("seen-missing")
        result = self.run_cli("--session", "seen-missing", "add", "--url", "https://a.cn/1", ok=False)
        self.assertIn("--backend", result.stderr)
        result = self.run_cli(
            "--session", "seen-missing", "add", "--backend", "exa", "--url", "https://a.cn/1", ok=False
        )
        self.assertIn("--query", result.stderr)

    def test_user_provided_rejects_backend_fields(self) -> None:
        self.start_session("up-conflict")
        result = self.run_cli(
            "--session",
            "up-conflict",
            "add",
            "--user-provided",
            "--backend",
            "exa",
            "--url",
            "https://a.cn/1",
            ok=False,
        )
        self.assertIn("--user-provided", result.stderr)

    def test_rejects_non_http_url(self) -> None:
        self.start_session("bad-url")
        for url in ("ftp://example.com/file", "not-a-url", "https://"):
            result = self.run_cli(
                "--session",
                "bad-url",
                "add",
                "--backend",
                "exa",
                "--query",
                "q",
                "--url",
                url,
                ok=False,
            )
            self.assertIn("http(s)", result.stderr)

    def test_requires_existing_session(self) -> None:
        result = self.run_cli("--session", "ghost", "add", "--url", "https://a.cn/1", ok=False)
        self.assertIn("does not exist", result.stderr)
        result = self.run_cli("--session", "ghost", "list", ok=False)
        self.assertIn("does not exist", result.stderr)

    def test_active_session_fallback(self) -> None:
        # start sets the active-session pointer; evidence commands resolve it.
        self.start_session("active-fallback")
        result = self.run_cli("add", "--backend", "tavily", "--query", "q", "--url", "https://a.cn/1")
        self.assertIn("SESSION:active-fallback", result.stdout)
        self.assertIn("OK:Recorded 1 evidence record(s)", result.stdout)

    def test_start_rejects_session_with_stale_ledger(self) -> None:
        # Resetting by deleting only the state JSON must not silently
        # inherit the old ledger — those URLs would pass the done audit
        # as if seen by the NEW session.
        self.start_session("stale-ledger")
        self.run_cli(
            "--session", "stale-ledger", "add", "--backend", "exa", "--query", "q", "--url", "https://old.cn/1"
        )
        (self.state_dir / "stale-ledger.json").unlink()
        result = self.run_state_cli("--session", "stale-ledger", "start", ok=False)
        self.assertIn("evidence ledger already exists", result.stderr)


class EvidenceListTests(EvidenceCliHarness, unittest.TestCase):
    def test_kind_filter(self) -> None:
        self.start_session("kind-filter")
        self.run_cli("--session", "kind-filter", "add", "--backend", "exa", "--query", "q", "--url", "https://a.cn/1")
        self.run_cli("--session", "kind-filter", "add", "--user-provided", "--url", "https://b.cn/2")
        seen = self.list_records("kind-filter", "--kind", "seen")
        self.assertEqual([r["kind"] for r in seen], ["seen"])
        provided = self.list_records("kind-filter", "--kind", "user_provided")
        self.assertEqual([r["kind"] for r in provided], ["user_provided"])

    def test_list_missing_ledger_is_empty(self) -> None:
        self.start_session("no-ledger")
        self.assertEqual(self.list_records("no-ledger"), [])


class EvidenceDurabilityTests(EvidenceCliHarness, unittest.TestCase):
    def test_concurrent_adds_do_not_lose_rows(self) -> None:
        self.start_session("concurrent")
        workers = 4
        urls_per_worker = 3
        processes = []
        for worker in range(workers):
            args = [
                sys.executable,
                str(SCRIPT),
                "--state-dir",
                str(self.state_dir),
                "--session",
                "concurrent",
                "add",
                "--backend",
                f"backend-{worker}",
                "--query",
                "q",
            ]
            for i in range(urls_per_worker):
                args.extend(["--url", f"https://w{worker}.cn/{i}"])
            processes.append(subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        for process in processes:
            _stdout, stderr = process.communicate(timeout=60)
            self.assertEqual(process.returncode, 0, f"concurrent add failed: {stderr!r}")
        records = self.list_records("concurrent")
        self.assertEqual(len(records), workers * urls_per_worker)

    def test_truncated_last_line_is_dropped(self) -> None:
        self.start_session("truncated")
        self.run_cli("--session", "truncated", "add", "--backend", "exa", "--query", "q", "--url", "https://a.cn/1")
        self.run_cli("--session", "truncated", "add", "--backend", "exa", "--query", "q", "--url", "https://b.cn/2")
        with self.ledger_path("truncated").open("a", encoding="utf-8", newline="") as handle:
            handle.write('{"kind":"seen","ts":"20')  # crash mid-append, no newline
        result = self.run_cli("--session", "truncated", "list")
        self.assertIn("WARNING:dropped truncated last line", result.stderr)
        self.assertEqual(len(self.list_records("truncated")), 2)

    def test_corrupt_middle_line_is_error(self) -> None:
        self.start_session("corrupt-mid")
        self.run_cli("--session", "corrupt-mid", "add", "--backend", "exa", "--query", "q", "--url", "https://a.cn/1")
        with self.ledger_path("corrupt-mid").open("a", encoding="utf-8", newline="") as handle:
            handle.write("garbage-not-json\n")
            handle.write('{"kind":"seen","ts":"t","backend":"x","query":"q","url":"https://c.cn/3"}\n')
        result = self.run_cli("--session", "corrupt-mid", "list", ok=False)
        self.assertIn("corrupt ledger line", result.stderr)


class EvidenceSealingTests(EvidenceCliHarness, unittest.TestCase):
    def test_add_rejected_after_done(self) -> None:
        self.drive_to_done("sealed")
        before = self.list_records("sealed")
        self.assertEqual(len(before), 10)  # registered by drive_to_done
        result = self.run_cli(
            "--session", "sealed", "add", "--backend", "exa", "--query", "q", "--url", "https://late.cn/1", ok=False
        )
        self.assertIn("sealed", result.stderr)
        # The failed add must not have written: ledger byte-count unchanged.
        self.assertEqual(self.list_records("sealed"), before)

    def test_add_allowed_again_after_add_dimensions(self) -> None:
        self.drive_to_done("reopen")
        extension = json.dumps({"keywords_zh": ["新维度"], "keywords_en": ["new dimension"]}, ensure_ascii=False)
        self.run_state_cli("--session", "reopen", "add_dimensions", extension)
        self.run_cli("--session", "reopen", "add", "--backend", "exa", "--query", "新维度", "--url", "https://d.cn/4")
        # 10 records from drive_to_done's registration + 1 after reopening.
        self.assertEqual(len(self.list_records("reopen")), 11)


class EvidenceAuditTests(EvidenceCliHarness, unittest.TestCase):
    """Evidence Audit: report references against the ledger, done hard gate."""

    def write_ref_report(self, name: str, refs: list[str]) -> Path:
        """Minimal report with just a 参考文献 section (audit only reads it)."""
        report = Path(self.temp_dir.name) / name
        report.write_text("# 测试\n\n## 参考文献\n" + "\n".join(refs) + "\n", encoding="utf-8")
        return report

    @staticmethod
    def ref_line(number: int, url: str) -> str:
        return f"[{number}] 作者 — 研究 — {url} — 2025 — 层级: 1 — 来源: Exa"

    def test_audit_passes_when_all_traced(self) -> None:
        self.start_session("audit-ok")
        report = self.write_ref_report(
            "audit-ok.md",
            [self.ref_line(1, "https://a.cn/one"), self.ref_line(2, "https://b.org/two")],
        )
        self.run_cli(
            "--session",
            "audit-ok",
            "add",
            "--backend",
            "exa",
            "--query",
            "q",
            "--url",
            "https://a.cn/one",
            "--url",
            "https://b.org/two",
        )
        result = self.run_cli("--session", "audit-ok", "audit", "--report", str(report))
        self.assertIn("OK:all 2 reference URL(s) traced", result.stdout)

    def test_audit_lists_untraced_with_numbers(self) -> None:
        self.start_session("audit-miss")
        report = self.write_ref_report(
            "audit-miss.md",
            [self.ref_line(1, "https://a.cn/one"), self.ref_line(2, "https://fabricated.cn/ghost")],
        )
        self.run_cli("--session", "audit-miss", "add", "--backend", "exa", "--query", "q", "--url", "https://a.cn/one")
        result = self.run_cli("--session", "audit-miss", "audit", "--report", str(report), ok=False)
        self.assertIn("UNTRACED:[2] https://fabricated.cn/ghost", result.stdout)
        self.assertIn("evidence audit failed: 1/2", result.stderr)

    def test_audit_missing_ledger_guides_registration(self) -> None:
        self.start_session("audit-empty")
        report = self.write_ref_report("audit-empty.md", [self.ref_line(1, "https://a.cn/one")])
        result = self.run_cli("--session", "audit-empty", "audit", "--report", str(report), ok=False)
        self.assertIn("1/1", result.stderr)
        self.assertIn("evidence.py add", result.stderr)

    def test_audit_normalizes_tracking_params(self) -> None:
        self.start_session("audit-norm")
        # Report URL carries tracking params the ledger URL does not have.
        report = self.write_ref_report(
            "audit-norm.md",
            [self.ref_line(1, "https://a.cn/one?utm_source=x&fbclid=y")],
        )
        self.run_cli("--session", "audit-norm", "add", "--backend", "exa", "--query", "q", "--url", "https://a.cn/one")
        result = self.run_cli("--session", "audit-norm", "audit", "--report", str(report))
        self.assertIn("OK:all 1 reference URL(s) traced", result.stdout)

    def test_audit_user_provided_counts_as_hit(self) -> None:
        self.start_session("audit-up")
        report = self.write_ref_report("audit-up.md", [self.ref_line(1, "https://gov.cn/report.pdf")])
        self.run_cli("--session", "audit-up", "add", "--user-provided", "--url", "https://gov.cn/report.pdf")
        result = self.run_cli("--session", "audit-up", "audit", "--report", str(report))
        self.assertIn("OK:all 1 reference URL(s) traced", result.stdout)

    def test_audit_rejects_unknown_session(self) -> None:
        result = self.run_cli("--session", "ghost", "audit", "--report", "x.md", ok=False)
        self.assertIn("does not exist", result.stderr)

    def test_done_gate_fails_then_fixes_via_registration(self) -> None:
        # Unregistered: done fails with the audit error.
        self.start_session("gate")
        params = json.dumps(
            {
                "topic": "人工智能与劳动分配",
                "min_sources": 10,
                "keywords_zh": ["人工智能"],
                "keywords_en": ["artificial intelligence"],
            },
            ensure_ascii=False,
        )
        self.run_state_cli("--session", "gate", "set_params", params)
        report = Path(self.temp_dir.name) / "gate.md"
        make_valid_report(report)
        result = self.run_state_cli("--session", "gate", "done", "--report", str(report), ok=False)
        self.assertIn("evidence audit failed", result.stderr)
        self.assertIn("untraced", result.stderr)
        # Register every reference URL exactly as a Lead would, then done passes.
        urls = report_reference_urls(report)
        self.assertEqual(len(urls), 10)
        add_args = ["--session", "gate", "add", "--backend", "exa", "--query", "q"]
        for url in urls:
            add_args.extend(["--url", url])
        self.run_cli(*add_args)
        done = self.run_state_cli("--session", "gate", "done", "--report", str(report))
        self.assertIn("STATE:DONE", done.stdout)

    def test_done_with_corrupt_ledger_prints_error_not_traceback(self) -> None:
        # Regression: evidence's StateError must be the SAME class the
        # state_machine CLI catches, or `done` dies with a raw traceback
        # instead of the ERROR: line contract.
        self.start_session("corrupt-done")
        params = json.dumps(
            {
                "topic": "人工智能与劳动分配",
                "min_sources": 10,
                "keywords_zh": ["人工智能"],
                "keywords_en": ["artificial intelligence"],
            },
            ensure_ascii=False,
        )
        self.run_state_cli("--session", "corrupt-done", "set_params", params)
        report = Path(self.temp_dir.name) / "corrupt-done.md"
        make_valid_report(report)
        register_report_evidence(self.state_dir, "corrupt-done", report)
        ledger = self.ledger_path("corrupt-done")
        lines = ledger.read_text(encoding="utf-8").splitlines()
        lines[4] = "garbage-not-json"
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
        result = self.run_state_cli("--session", "corrupt-done", "done", "--report", str(report), ok=False)
        self.assertTrue(result.stderr.startswith("ERROR:"), msg=result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("corrupt ledger line", result.stderr)

    def test_audit_fails_for_wrong_report_content(self) -> None:
        # A report whose references were never seen must not slip through
        # just because the ledger has OTHER urls registered.
        self.start_session("audit-other")
        report = self.write_ref_report("audit-other.md", [self.ref_line(1, "https://never-seen.cn/x")])
        self.run_cli(
            "--session", "audit-other", "add", "--backend", "exa", "--query", "q", "--url", "https://unrelated.cn/y"
        )
        result = self.run_cli("--session", "audit-other", "audit", "--report", str(report), ok=False)
        self.assertIn("UNTRACED:[1]", result.stdout)


class EvidenceLedgerIntegrityTests(EvidenceCliHarness, unittest.TestCase):
    """Ledger fingerprint in the DONE proof: `check` verifies report AND ledger."""

    def test_done_proof_records_ledger_fingerprint(self) -> None:
        self.drive_to_done("fingerprinted")
        state = json.loads((self.state_dir / "fingerprinted.json").read_text(encoding="utf-8"))
        proof = state["report_validation"]
        self.assertEqual(proof["evidence_lines"], 10)
        expected_sha = hashlib.sha256(self.ledger_path("fingerprinted").read_bytes()).hexdigest()
        self.assertEqual(proof["evidence_sha256"], expected_sha)

    def test_check_ok_when_ledger_unchanged(self) -> None:
        self.drive_to_done("ledger-ok")
        result = self.run_state_cli("--session", "ledger-ok", "check")
        self.assertIn("INTEGRITY:OK", result.stdout)

    def test_check_detects_ledger_append_after_done(self) -> None:
        # Bypasses the sealed `add`: simulates a backdated row written
        # straight into the jsonl after DONE.
        self.drive_to_done("backdated")
        record = json.dumps(
            {
                "kind": "seen",
                "ts": "2026-01-01T00:00+00:00",
                "backend": "exa",
                "query": "q",
                "url": "https://backdated.cn/1",
            },
            ensure_ascii=False,
        )
        with self.ledger_path("backdated").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(record + "\n")
        result = self.run_state_cli("--session", "backdated", "check", ok=False)
        self.assertIn("INTEGRITY:MISMATCH", result.stdout)
        self.assertEqual(result.returncode, 1)

    def test_check_detects_deleted_ledger(self) -> None:
        self.drive_to_done("ledger-gone")
        self.ledger_path("ledger-gone").unlink()
        result = self.run_state_cli("--session", "ledger-gone", "check", ok=False)
        self.assertIn("INTEGRITY:MISSING", result.stdout)
        self.assertEqual(result.returncode, 1)

    def test_redone_after_extension_refreshes_fingerprint(self) -> None:
        self.drive_to_done("refresh")
        first = json.loads((self.state_dir / "refresh.json").read_text(encoding="utf-8"))
        first_sha = first["report_validation"]["evidence_sha256"]
        extension = json.dumps({"keywords_zh": ["追加维度"]}, ensure_ascii=False)
        self.run_state_cli("--session", "refresh", "add_dimensions", extension)
        report = Path(self.temp_dir.name) / "refresh.md"
        make_valid_report(report)
        register_report_evidence(self.state_dir, "refresh", report, backend="test2")
        self.run_state_cli("--session", "refresh", "done", "--report", str(report))
        second = json.loads((self.state_dir / "refresh.json").read_text(encoding="utf-8"))
        # Ledger grew, so the refreshed proof fingerprints different bytes.
        self.assertNotEqual(second["report_validation"]["evidence_sha256"], first_sha)
        self.assertEqual(second["report_validation"]["evidence_lines"], 20)
        # And check is green against the refreshed fingerprint.
        result = self.run_state_cli("--session", "refresh", "check")
        self.assertIn("INTEGRITY:OK", result.stdout)


if __name__ == "__main__":
    unittest.main()

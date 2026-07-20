from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "state_machine.py"


class StateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name) / "state"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str, ok: bool = True, env: dict[str, str] | None = None):
        command = [
            sys.executable,
            str(SCRIPT),
            "--state-dir",
            str(self.state_dir),
            *args,
        ]
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        if ok and result.returncode != 0:
            self.fail(
                f"command failed: {command}\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        if not ok and result.returncode == 0:
            self.fail(
                f"command unexpectedly succeeded: {command}\nstdout={result.stdout}"
            )
        return result

    def write_valid_report(
        self,
        name: str = "report.md",
        *,
        duplicate_urls: bool = False,
        topic: str = "人工智能与劳动分配",
        source_count: int = 10,
    ) -> Path:
        report = Path(self.temp_dir.name) / name
        citations = "".join(f"[{number}]" for number in range(1, source_count + 1))
        references = []
        for number in range(1, source_count + 1):
            title = "中文来源" if number % 2 == 0 else "English source"
            url_number = 1 if duplicate_urls else number
            references.append(
                f"[{number}] Organization — {title} — "
                f"https://example.com/source-{url_number} — 2025 — "
                "Tier: 1 — Found by: AnySearch"
            )
        report.write_text(
            f"""# {topic}

## TL;DR
中文结论 with international evidence {citations}。

## 搜索与降级状态
AnySearch: available; Tavily: quota_exhausted; SciVerse: unavailable.

## 参考文献
{chr(10).join(references)}
""",
            encoding="utf-8",
        )
        return report

    def set_params(
        self, session: str, *, topic: str = "人工智能与劳动分配", min_sources: int = 10
    ) -> None:
        params = json.dumps(
            {
                "topic": topic,
                "min_sources": min_sources,
                "keywords_zh": ["人工智能", "劳动分配"],
                "keywords_en": ["artificial intelligence", "labor allocation"],
                "time_range": "all",
            },
            ensure_ascii=False,
        )
        self.run_cli("--session", session, "set_params", params)

    def record_agent_cycle(self, session: str, agent_id: str = "agent-1") -> Path:
        self.run_cli(
            "--session",
            session,
            "record_dispatch",
            agent_id,
            "--objective",
            "Research one independent mechanism",
            "--dispatch-ref",
            f"dispatch-{agent_id}",
        )
        result_path = Path(self.temp_dir.name) / f"{session}-{agent_id}.md"
        result_path.write_text(
            "# Findings\n\nEvidence with source URLs.\n", encoding="utf-8"
        )
        return result_path

    def advance_to_s3(self, session: str) -> None:
        self.run_cli("--session", session, "init")
        self.set_params(session)
        self.run_cli("--session", session, "advance", "S1")
        result_path = self.record_agent_cycle(session)
        self.run_cli("--session", session, "advance", "S2")
        self.run_cli(
            "--session",
            session,
            "record_result",
            "agent-1",
            "--result",
            str(result_path),
        )
        self.run_cli("--session", session, "advance", "S3")

    def test_full_workflow_and_params(self) -> None:
        self.run_cli("--session", "ai-labor", "init")
        params = json.dumps(
            {
                "topic": "人工智能与劳动分配",
                "min_sources": 10,
                "keywords_zh": ["人工智能", "劳动分配", "收入分配"],
                "keywords_en": ["artificial intelligence", "labor allocation"],
                "time_range": "all",
            },
            ensure_ascii=False,
        )
        self.run_cli("--session", "ai-labor", "set_params", params)
        loaded = self.run_cli("--session", "ai-labor", "get_params")
        self.assertEqual(json.loads(loaded.stdout), json.loads(params))

        result = self.run_cli("--session", "ai-labor", "advance", "S1")
        self.assertIn("STATE:S1", result.stdout)
        result_path = self.record_agent_cycle("ai-labor")
        result = self.run_cli("--session", "ai-labor", "advance", "S2")
        self.assertIn("STATE:S2", result.stdout)
        self.run_cli(
            "--session",
            "ai-labor",
            "record_result",
            "agent-1",
            "--result",
            str(result_path),
        )
        result = self.run_cli("--session", "ai-labor", "advance", "S3")
        self.assertIn("STATE:S3", result.stdout)
        report = self.write_valid_report()
        result = self.run_cli(
            "--session",
            "ai-labor",
            "advance",
            "DONE",
            "--report",
            str(report),
            "--min-sources",
            "10",
        )
        self.assertIn("STATE:DONE", result.stdout)
        self.assertIn(f"REPORT:{report.resolve()}", result.stdout)
        self.assertEqual(
            self.run_cli("--session", "ai-labor", "get_phase").stdout.strip(), "DONE"
        )

        state = json.loads(
            (self.state_dir / "ai-labor.json").read_text(encoding="utf-8")
        )
        proof = state["report_validation"]
        self.assertEqual(proof["min_sources"], 10)
        self.assertEqual(proof["topic"], "人工智能与劳动分配")
        self.assertEqual(
            proof["sha256"], hashlib.sha256(report.read_bytes()).hexdigest()
        )
        self.assertEqual(state["history"][-1]["event"], "REPORT_VALIDATED")
        self.assertEqual(state["agents"]["agent-1"]["status"], "returned")
        self.assertEqual(
            state["agents"]["agent-1"]["result_sha256"],
            hashlib.sha256(result_path.read_bytes()).hexdigest(),
        )

        checked = self.run_cli("--session", "ai-labor", "check")
        self.assertIn("INTEGRITY:OK", checked.stdout)

    def test_done_requires_a_report(self) -> None:
        self.advance_to_s3("missing-report")
        result = self.run_cli(
            "--session", "missing-report", "advance", "DONE", ok=False
        )
        self.assertIn("requires --report", result.stderr)
        self.assertEqual(
            self.run_cli("--session", "missing-report", "get_phase").stdout.strip(),
            "S3",
        )

    def test_done_rejects_an_invalid_report_without_advancing(self) -> None:
        self.advance_to_s3("invalid-report")
        report = Path(self.temp_dir.name) / "invalid.md"
        report.write_text("# Missing required report sections\n", encoding="utf-8")
        result = self.run_cli(
            "--session",
            "invalid-report",
            "advance",
            "DONE",
            "--report",
            str(report),
            ok=False,
        )
        self.assertIn("report validation failed", result.stderr)
        self.assertEqual(
            self.run_cli("--session", "invalid-report", "get_phase").stdout.strip(),
            "S3",
        )

    def test_done_rejects_a_threshold_below_the_skill_floor(self) -> None:
        self.advance_to_s3("low-threshold")
        report = self.write_valid_report("low-threshold.md")
        result = self.run_cli(
            "--session",
            "low-threshold",
            "advance",
            "DONE",
            "--report",
            str(report),
            "--min-sources",
            "1",
            ok=False,
        )
        self.assertIn("must be at least 10", result.stderr)
        self.assertEqual(
            self.run_cli("--session", "low-threshold", "get_phase").stdout.strip(),
            "S3",
        )

    def test_done_rejects_threshold_different_from_confirmed_scope(self) -> None:
        self.advance_to_s3("bound-threshold")
        report = self.write_valid_report("bound-threshold.md", source_count=12)
        result = self.run_cli(
            "--session",
            "bound-threshold",
            "advance",
            "DONE",
            "--report",
            str(report),
            "--min-sources",
            "12",
            ok=False,
        )
        self.assertIn("does not match confirmed min_sources", result.stderr)

    def test_done_rejects_report_for_another_topic(self) -> None:
        self.advance_to_s3("bound-topic")
        report = self.write_valid_report("wrong-topic.md", topic="量子芯片供应链")
        result = self.run_cli(
            "--session",
            "bound-topic",
            "advance",
            "DONE",
            "--report",
            str(report),
            ok=False,
        )
        self.assertIn("confirmed topic", result.stderr)

    def test_check_rejects_report_changed_after_done(self) -> None:
        self.advance_to_s3("changed-report")
        report = self.write_valid_report("changed-report.md")
        self.run_cli(
            "--session", "changed-report", "advance", "DONE", "--report", str(report)
        )
        report.write_text(
            report.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8"
        )
        result = self.run_cli("--session", "changed-report", "check", ok=False)
        self.assertIn("report hash mismatch", result.stderr)
        phase = self.run_cli("--session", "changed-report", "get_phase", ok=False)
        self.assertIn("report hash mismatch", phase.stderr)

    def test_done_rejects_duplicate_source_urls(self) -> None:
        self.advance_to_s3("duplicate-urls")
        report = self.write_valid_report("duplicate-urls.md", duplicate_urls=True)
        result = self.run_cli(
            "--session",
            "duplicate-urls",
            "advance",
            "DONE",
            "--report",
            str(report),
            "--min-sources",
            "10",
            ok=False,
        )
        self.assertIn("reference URLs are not unique", result.stderr)
        self.assertEqual(
            self.run_cli("--session", "duplicate-urls", "get_phase").stdout.strip(),
            "S3",
        )

    def test_rejects_invalid_transition(self) -> None:
        self.run_cli("--session", "invalid-transition", "init")
        result = self.run_cli(
            "--session", "invalid-transition", "advance", "S2", ok=False
        )
        self.assertIn("expected S1", result.stderr)

    def test_s1_requires_confirmed_params(self) -> None:
        self.run_cli("--session", "missing-params", "init")
        result = self.run_cli("--session", "missing-params", "advance", "S1", ok=False)
        self.assertIn("set_params", result.stderr)

    def test_params_require_topic_and_source_threshold_and_are_immutable(self) -> None:
        self.run_cli("--session", "params-contract", "init")
        missing = self.run_cli(
            "--session",
            "params-contract",
            "set_params",
            json.dumps({"topic": "人工智能"}, ensure_ascii=False),
            ok=False,
        )
        self.assertIn("min_sources", missing.stderr)
        self.set_params("params-contract")
        repeated = self.run_cli(
            "--session",
            "params-contract",
            "set_params",
            json.dumps({"topic": "changed", "min_sources": 10}),
            ok=False,
        )
        self.assertIn("already been set", repeated.stderr)

    def test_s2_requires_dispatch_ledger(self) -> None:
        self.run_cli("--session", "dispatch-gate", "init")
        self.set_params("dispatch-gate")
        self.run_cli("--session", "dispatch-gate", "advance", "S1")
        result = self.run_cli("--session", "dispatch-gate", "advance", "S2", ok=False)
        self.assertIn("dispatch evidence", result.stderr)

    def test_s3_requires_all_agent_results(self) -> None:
        self.run_cli("--session", "result-gate", "init")
        self.set_params("result-gate")
        self.run_cli("--session", "result-gate", "advance", "S1")
        self.record_agent_cycle("result-gate")
        self.run_cli("--session", "result-gate", "advance", "S2")
        result = self.run_cli("--session", "result-gate", "advance", "S3", ok=False)
        self.assertIn("not terminal", result.stderr)

    def test_duplicate_init_does_not_overwrite(self) -> None:
        self.run_cli("--session", "duplicate", "init")
        self.set_params("duplicate")
        self.run_cli("--session", "duplicate", "advance", "S1")
        result = self.run_cli("--session", "duplicate", "init", ok=False)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(
            self.run_cli("--session", "duplicate", "get_phase").stdout.strip(), "S1"
        )

    def test_force_init_is_not_available(self) -> None:
        self.run_cli("--session", "no-force", "init")
        result = self.run_cli("--force", "--session", "no-force", "init", ok=False)
        self.assertIn("unrecognized arguments", result.stderr)
        self.assertEqual(
            self.run_cli("--session", "no-force", "get_phase").stdout.strip(), "S0"
        )

    def test_sessions_are_isolated(self) -> None:
        self.run_cli("--session", "session-a", "init")
        self.set_params("session-a")
        self.run_cli("--session", "session-a", "advance", "S1")
        self.run_cli("--session", "session-b", "init")
        self.assertEqual(
            self.run_cli("--session", "session-a", "get_phase").stdout.strip(), "S1"
        )
        self.assertEqual(
            self.run_cli("--session", "session-b", "get_phase").stdout.strip(), "S0"
        )

    def test_tri_research_home_is_not_used_as_state_dir(self) -> None:
        skill_home = Path(self.temp_dir.name) / "skill-home"
        skill_home.mkdir()
        env = os.environ.copy()
        env["TRI_RESEARCH_HOME"] = str(skill_home)
        env.pop("TRI_RESEARCH_STATE_DIR", None)
        self.run_cli("--session", "no-pollution", "init", env=env)
        self.assertEqual(list(skill_home.iterdir()), [])

    def test_rejects_path_traversal_session_id(self) -> None:
        result = self.run_cli("--session", "../escape", "init", ok=False)
        self.assertIn("session id must match", result.stderr)


if __name__ == "__main__":
    unittest.main()

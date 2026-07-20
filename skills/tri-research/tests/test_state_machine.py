from __future__ import annotations

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
        command = [sys.executable, str(SCRIPT), "--state-dir", str(self.state_dir), *args]
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        if ok and result.returncode != 0:
            self.fail(f"command failed: {command}\nstdout={result.stdout}\nstderr={result.stderr}")
        if not ok and result.returncode == 0:
            self.fail(f"command unexpectedly succeeded: {command}\nstdout={result.stdout}")
        return result

    def test_full_workflow_and_params(self) -> None:
        self.run_cli("--session", "ai-labor", "init")
        params = json.dumps(
            {
                "topic": "人工智能与劳动分配",
                "keywords_zh": ["人工智能", "劳动分配", "收入分配"],
                "keywords_en": ["artificial intelligence", "labor allocation"],
                "time_range": "all",
            },
            ensure_ascii=False,
        )
        self.run_cli("--session", "ai-labor", "set_params", params)
        loaded = self.run_cli("--session", "ai-labor", "get_params")
        self.assertEqual(json.loads(loaded.stdout), json.loads(params))

        expected = ["S1", "S2", "S3", "DONE"]
        for phase in expected:
            result = self.run_cli("--session", "ai-labor", "advance", phase)
            self.assertIn(f"STATE:{phase}", result.stdout)
        self.assertEqual(
            self.run_cli("--session", "ai-labor", "get_phase").stdout.strip(), "DONE"
        )

    def test_rejects_invalid_transition(self) -> None:
        self.run_cli("--session", "invalid-transition", "init")
        result = self.run_cli(
            "--session", "invalid-transition", "advance", "S2", ok=False
        )
        self.assertIn("expected S1", result.stderr)

    def test_duplicate_init_does_not_overwrite(self) -> None:
        self.run_cli("--session", "duplicate", "init")
        self.run_cli("--session", "duplicate", "advance", "S1")
        result = self.run_cli("--session", "duplicate", "init", ok=False)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(
            self.run_cli("--session", "duplicate", "get_phase").stdout.strip(), "S1"
        )

    def test_sessions_are_isolated(self) -> None:
        self.run_cli("--session", "session-a", "init")
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

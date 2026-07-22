"""Regression tests for get_phase / get_params output consistency.

Bug: state_machine.py's `check` command emits SESSION: and FILE: lines
along with STATE:. But `get_phase` and `get_params` only emit the value
itself (e.g. "DONE" or the params JSON) — no SESSION: or FILE: marker.
External consumers that parse the output (e.g. CI scripts, status
dashboards) cannot tell which session a value belongs to when these
commands are run without --session (the active session is implicit).

Contract: every read-only command that produces output for a given
session must include the session id in a parseable form, so a script
running `get_phase` on multiple sessions (or against an active-session
fallback) can attribute the result.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parents[3]
SCRIPT = REPO / "skills" / "tri-research" / "scripts" / "state_machine.py"


def _load_state_machine():
    spec = importlib.util.spec_from_file_location(
        "sm_under_test_xyz", str(SCRIPT)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class GetCommandsConsistencyTests(unittest.TestCase):
    def test_get_phase_emits_session_marker(self) -> None:
        """`get_phase` output must include a SESSION: line so consumers
        can attribute the phase value to a specific session id."""
        _load_state_machine()  # ensure module loads before subprocess test
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            state_dir = Path(tmp) / "state"
            proc = subprocess.run(
                [
                    sys.executable, str(SCRIPT),
                    "--state-dir", str(state_dir),
                    "--session", "consistency-1",
                    "start",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            # Now query get_phase
            proc = subprocess.run(
                [
                    sys.executable, str(SCRIPT),
                    "--state-dir", str(state_dir),
                    "--session", "consistency-1",
                    "get_phase",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            # Contract: stdout must contain a SESSION: marker.
            self.assertIn(
                "SESSION:consistency-1", proc.stdout,
                msg=f"get_phase output missing SESSION marker: {proc.stdout!r}",
            )

    def test_get_params_emits_session_marker(self) -> None:
        """`get_params` output must include a SESSION: line so consumers
        can attribute the params JSON to a specific session id."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            state_dir = Path(tmp) / "state"
            params = json.dumps({
                "topic": "t", "min_sources": 10,
                "keywords_zh": ["a"], "keywords_en": ["b"],
            }, ensure_ascii=False)
            for args in (
                ["--state-dir", str(state_dir), "--session", "consistency-2", "start"],
                ["--state-dir", str(state_dir), "--session", "consistency-2",
                 "set_params", params],
                ["--state-dir", str(state_dir), "--session", "consistency-2",
                 "get_params"],
            ):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT), *args],
                    capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
            last = proc
            self.assertIn(
                "SESSION:consistency-2", last.stdout,
                msg=f"get_params output missing SESSION marker: {last.stdout!r}",
            )


if __name__ == "__main__":
    unittest.main()

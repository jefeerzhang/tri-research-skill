"""Regression tests for active-session lifecycle.

Bug: state_machine.py's `done` step sets the session to phase=DONE but
leaves the `active-session` pointer file pointing at the just-completed
session. The next caller who runs `check` / `get_phase` / `get_params`
without --session will silently be served the completed session's
output, masking the fact that they have not started a new session.

Contract: after `done` transitions a session to DONE, the active-session
pointer must NOT point at it. The pointer is the "what would a brand-new
caller operate on" — pointing at a done session violates that semantic.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parents[3]
SCRIPT = REPO / "skills" / "tri-research" / "scripts" / "state_machine.py"


class ActiveSessionAfterDoneTests(unittest.TestCase):
    def test_done_clears_active_session_pointer(self) -> None:
        """After a successful `done` step, `active-session` should not
        point at the completed session — otherwise the next caller who
        forgets --session is silently served the done session's state."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            state_dir = Path(tmp) / "state"
            session = "active-after-done"

            def run(*args: str, ok: bool = True):
                import subprocess
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT),
                     "--state-dir", str(state_dir), *args],
                    capture_output=True, text=True,
                )
                if ok and proc.returncode != 0:
                    self.fail(f"command failed: {args}\nstdout={proc.stdout}\nstderr={proc.stderr}")
                if not ok and proc.returncode == 0:
                    self.fail(f"command unexpectedly succeeded: {args}\nstdout={proc.stdout}")
                return proc

            # Set up: start, set params, run done on the sample report.
            import json
            params = json.dumps({
                "topic": "人工智能与劳动分配", "min_sources": 10,
                "keywords_zh": ["人工智能"], "keywords_en": ["ai"],
            }, ensure_ascii=False)
            run("--session", session, "start")
            run("--session", session, "set_params", params)
            sample = REPO / "examples" / "DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md"
            run("--session", session, "done", "--report", str(sample))

            # Contract: after DONE, the active-session pointer must not
            # serve the completed session. Two acceptable shapes:
            #   (a) the file no longer exists (no active session), or
            #   (b) the file exists but its content is not the done session
            # Either way, running a read command with no --session must
            # NOT silently operate on the completed session.
            active_file = state_dir / "active-session"
            if active_file.exists():
                content = active_file.read_text(encoding="utf-8").strip()
                self.assertNotEqual(
                    content, session,
                    msg=(
                        f"active-session still points at done session {session!r}; "
                        f"the pointer must be cleared or point at a new active session "
                        f"after DONE, otherwise subsequent no-arg commands will "
                        f"silently serve the completed session's state."
                    ),
                )

    def test_done_does_not_clear_unrelated_active_session(self) -> None:
        """Completing session B must not wipe active-session when it points at A."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            state_dir = Path(tmp) / "state"
            sample = REPO / "examples" / "DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md"

            def run(*args: str, ok: bool = True):
                import subprocess
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT),
                     "--state-dir", str(state_dir), *args],
                    capture_output=True, text=True,
                )
                if ok and proc.returncode != 0:
                    self.fail(f"command failed: {args}\nstdout={proc.stdout}\nstderr={proc.stderr}")
                if not ok and proc.returncode == 0:
                    self.fail(f"command unexpectedly succeeded: {args}\nstdout={proc.stdout}")
                return proc

            import json
            params = json.dumps({
                "topic": "人工智能与劳动分配", "min_sources": 10,
                "keywords_zh": ["人工智能"], "keywords_en": ["ai"],
            }, ensure_ascii=False)

            run("--session", "sess-A", "start")
            run("--session", "sess-A", "set_params", params)
            run("--session", "sess-B", "start")
            run("--session", "sess-B", "set_params", params)

            # Restore A as the active session while completing B explicitly.
            (state_dir / "active-session").write_text("sess-A\n", encoding="utf-8")
            run("--session", "sess-B", "done", "--report", str(sample))

            active_file = state_dir / "active-session"
            self.assertTrue(active_file.exists(), "active pointer for A must remain")
            self.assertEqual(active_file.read_text(encoding="utf-8").strip(), "sess-A")

            # no --session still resolves to A
            phase = run("get_phase")
            self.assertIn("SESSION:sess-A", phase.stdout)
            self.assertIn("STARTED", phase.stdout)


if __name__ == "__main__":
    unittest.main()

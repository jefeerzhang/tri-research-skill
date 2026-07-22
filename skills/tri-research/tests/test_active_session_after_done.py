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


if __name__ == "__main__":
    unittest.main()

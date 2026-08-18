"""Cross-process concurrency tests for the state machine.

The pre-lock implementation did a plain read-modify-write: two processes
running `done` (or `add_dimensions`) on the same session at the same time
could both load the state, mutate, and save — atomically, one after the
other — silently dropping each other's history entry and updated_at.

Contract: every mutating command (start / set_params / add_dimensions /
done) is serialized by a per-session lock taken for the whole command, so
N racing processes each append exactly one history entry and no mutation
is lost.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _test_helpers import make_valid_report

SKILL_ROOT = Path(__file__).parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "state_machine.py"


def run_cli(state_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--state-dir", str(state_dir), *args],
        capture_output=True,
        text=True,
    )


def build_valid_report(path: Path, *, topic: str = "人工智能与劳动分配", source_count: int = 10) -> None:
    make_valid_report(path, topic=topic, source_count=source_count)


class ConcurrencyTests(unittest.TestCase):
    def test_parallel_done_serializes_without_corruption(self) -> None:
        """Three processes racing `done` on the same session must serialize:
        exactly one wins and records a DONE entry, the other two fail loudly
        with 'already completed' (exit 1). Without the lock all three read
        phase=STARTED, all three write DONE and silently drop each other's
        history — the state still says DONE, so the loss is invisible."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            state_dir = Path(tmp) / "state"
            session = "race-done"
            report = Path(tmp) / "report.md"
            build_valid_report(report)

            start = run_cli(state_dir, "--session", session, "start")
            self.assertEqual(start.returncode, 0, msg=start.stderr)
            params = json.dumps(
                {
                    "topic": "人工智能与劳动分配",
                    "min_sources": 10,
                    "keywords_zh": ["人工智能"],
                    "keywords_en": ["artificial intelligence"],
                },
                ensure_ascii=False,
            )
            setp = run_cli(state_dir, "--session", session, "set_params", params)
            self.assertEqual(setp.returncode, 0, msg=setp.stderr)

            procs = [
                subprocess.Popen(
                    [sys.executable, str(SCRIPT), "--state-dir", str(state_dir),
                     "--session", session, "done", "--report", str(report)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(3)
            ]
            results = [proc.communicate(timeout=60) for proc in procs]
            codes = [proc.returncode for proc in procs]
            self.assertEqual(sorted(codes), [0, 1, 1])
            rejected = [err for _, err in results if "already completed" in err]
            self.assertEqual(len(rejected), 2)

            state = json.loads((state_dir / f"{session}.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "DONE")
            done_entries = [h for h in state["history"] if h["phase"] == "DONE"]
            self.assertEqual(len(done_entries), 1)

    def test_parallel_add_dimensions_loses_no_extension(self) -> None:
        """Two processes racing `add_dimensions` on the same session must
        both succeed and both extensions must be present. Without the lock
        the read-modify-write interleaves and one extension is lost."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            state_dir = Path(tmp) / "state"
            session = "race-extend"

            start = run_cli(state_dir, "--session", session, "start")
            self.assertEqual(start.returncode, 0, msg=start.stderr)
            params = json.dumps(
                {
                    "topic": "人工智能与劳动分配",
                    "min_sources": 10,
                    "keywords_zh": ["人工智能"],
                    "keywords_en": ["artificial intelligence"],
                },
                ensure_ascii=False,
            )
            setp = run_cli(state_dir, "--session", session, "set_params", params)
            self.assertEqual(setp.returncode, 0, msg=setp.stderr)

            extensions = [
                json.dumps({"keywords_zh": ["小米汽车"]}, ensure_ascii=False),
                json.dumps({"keywords_zh": ["低空经济"]}, ensure_ascii=False),
            ]
            procs = [
                subprocess.Popen(
                    [sys.executable, str(SCRIPT), "--state-dir", str(state_dir),
                     "--session", session, "add_dimensions", extensions[i]],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for i in range(2)
            ]
            for proc in procs:
                _, err = proc.communicate(timeout=60)
                self.assertEqual(proc.returncode, 0, msg=f"add_dimensions failed: {err}")

            state = json.loads((state_dir / f"{session}.json").read_text(encoding="utf-8"))
            keywords = state["params"]["keywords_zh"]
            self.assertEqual(
                sorted(keywords),
                ["人工智能", "低空经济", "小米汽车"],  # sorted() is by code point
                msg=f"a racing extension was lost: {keywords}",
            )
            self.assertEqual(len(state["history"]), 3)  # start, set_params, one EXTENDED per winner

    def test_parallel_start_single_winner(self) -> None:
        """Two processes racing `start` on the same session id: exactly one
        wins, the other fails with 'already exists' — and the state file is
        never corrupted."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            state_dir = Path(tmp) / "state"
            session = "race-start"

            procs = [
                subprocess.Popen(
                    [sys.executable, str(SCRIPT), "--state-dir", str(state_dir),
                     "--session", session, "start"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(2)
            ]
            results = [proc.communicate(timeout=60) for proc in procs]
            codes = [proc.returncode for proc in procs]

            self.assertEqual(sorted(codes), [0, 1])
            state_path = state_dir / f"{session}.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "STARTED")
            self.assertEqual(len(state["history"]), 1)


if __name__ == "__main__":
    unittest.main()

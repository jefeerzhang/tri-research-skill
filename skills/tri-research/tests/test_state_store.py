"""Direct unit tests for the session-aware StateStore interface.

These tests exercise the same seam as the CLI (StateStore methods) but
without spawning subprocesses. They lock in the orchestration behavior
that used to live in run(): lock-inside-method, phase guards, active
pointer lifecycle, and validation.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _test_helpers import load_module, make_valid_report

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"


def _params(**overrides):
    values = {
        "topic": "人工智能与劳动分配",
        "min_sources": 10,
        "keywords_zh": ["人工智能", "劳动分配"],
        "keywords_en": ["artificial intelligence", "labor allocation"],
    }
    values.update(overrides)
    return values


class StateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sm = load_module(SCRIPTS_DIR / "state_machine.py", "sm_store_test")
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.state_dir = Path(self.tmp.name) / "state"
        self.store = self.sm.StateStore(self.state_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_start_session_creates_state_and_active_pointer(self) -> None:
        data = self.store.start_session("s1")
        self.assertEqual(data["phase"], "STARTED")
        self.assertTrue((self.state_dir / "s1.json").exists())
        self.assertEqual(
            (self.state_dir / "active-session").read_text(encoding="utf-8").strip(),
            "s1",
        )

    def test_start_session_generates_default_id(self) -> None:
        data = self.store.start_session()
        # Second granularity: two researches opened within the same minute
        # must not collide on "session already exists".
        self.assertRegex(data["session_id"], r"^research-\d{8}-\d{6}$")
        self.assertTrue((self.state_dir / "active-session").exists())

    def test_start_session_rejects_duplicate(self) -> None:
        self.store.start_session("dup")
        with self.assertRaises(self.sm.StateError):
            self.store.start_session("dup")

    def test_set_params_validates_and_saves(self) -> None:
        self.store.start_session("s")
        data = self.store.set_params("s", _params())
        self.assertEqual(data["params"]["topic"], "人工智能与劳动分配")
        self.assertEqual(data["params"]["min_sources"], 10)

    def test_set_params_is_immutable(self) -> None:
        self.store.start_session("s")
        self.store.set_params("s", _params())
        with self.assertRaises(self.sm.StateError):
            self.store.set_params("s", _params(topic="changed"))

    def test_set_params_rejects_invalid(self) -> None:
        self.store.start_session("s")
        with self.assertRaises(self.sm.StateError):
            self.store.set_params("s", {"topic": "no min_sources"})

    def test_set_params_rejects_after_done(self) -> None:
        self.store.start_session("s")
        self.store.set_params("s", _params())
        report = Path(self.tmp.name) / "report.md"
        make_valid_report(report)
        self.store.complete("s", report)
        with self.assertRaises(self.sm.StateError) as ctx:
            self.store.set_params("s", _params(topic="changed"))
        self.assertIn("STARTED", str(ctx.exception))

    def test_extend_requires_params(self) -> None:
        self.store.start_session("s")
        with self.assertRaises(self.sm.StateError) as ctx:
            self.store.extend("s", {"keywords_zh": ["小米汽车"]})
        self.assertIn("parameters not set", str(ctx.exception))

    def test_complete_requires_params(self) -> None:
        self.store.start_session("s")
        report = Path(self.tmp.name) / "report.md"
        make_valid_report(report)
        with self.assertRaises(self.sm.StateError) as ctx:
            self.store.complete("s", report)
        self.assertIn("parameters not set", str(ctx.exception))

    def test_complete_returns_done_and_clears_active(self) -> None:
        self.store.start_session("s")
        self.store.set_params("s", _params())
        report = Path(self.tmp.name) / "report.md"
        make_valid_report(report)
        data = self.store.complete("s", report)
        self.assertEqual(data["phase"], "DONE")
        self.assertIn("report_validation", data)
        active = self.state_dir / "active-session"
        if active.exists():
            self.assertNotEqual(active.read_text(encoding="utf-8").strip(), "s")

    def test_complete_rejects_wrong_min_sources_override(self) -> None:
        self.store.start_session("s")
        self.store.set_params("s", _params())
        report = Path(self.tmp.name) / "report.md"
        make_valid_report(report)
        with self.assertRaises(self.sm.StateError):
            self.store.complete("s", report, min_sources=99)

    def test_extend_after_done_resets_active_and_clears_proof(self) -> None:
        self.store.start_session("s")
        self.store.set_params("s", _params())
        report = Path(self.tmp.name) / "report.md"
        make_valid_report(report)
        self.store.complete("s", report)

        data = self.store.extend("s", {"keywords_zh": ["小米汽车"]})
        self.assertEqual(data["phase"], "EXTENDED")
        self.assertNotIn("report_validation", data)
        self.assertIn("小米汽车", data["params"]["keywords_zh"])
        self.assertEqual(
            (self.state_dir / "active-session").read_text(encoding="utf-8").strip(),
            "s",
        )

    def test_atomic_write_uses_process_unique_temp_name(self) -> None:
        """Regression: the temp file for an atomic write must be per-process.

        The old deterministic ``<path>.tmp`` collided when two processes
        wrote the same path concurrently (two `start` commands for different
        sessions both updating the shared active-session pointer): one
        process replaced the temp file while the other still had it open
        (PermissionError on Windows) or was about to replace it
        (FileNotFoundError on POSIX).
        """
        import os
        from unittest import mock

        captured: list[str] = []
        real_replace = os.replace

        def spy_replace(src, dst):
            captured.append(str(src))
            return real_replace(src, dst)

        target = self.state_dir / "active-session"
        with mock.patch("os.replace", spy_replace):
            self.store._atomic_write_text(target, "s1\n")
        self.assertEqual(len(captured), 1)
        self.assertIn(f".{os.getpid()}.tmp", captured[0])
        self.assertEqual(target.read_text(encoding="utf-8"), "s1\n")


if __name__ == "__main__":
    unittest.main()

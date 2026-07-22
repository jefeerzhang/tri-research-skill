"""Regression tests for emit() behavior.

Bug: state_machine.py's emit() checks `if phase == "DONE" and
data.get("report_validation"):` to decide whether to print REPORT lines.
The `and` short-circuits silently when report_validation is missing,
so a DONE state that lacks report_validation prints nothing useful and
exits 0 — masking state corruption (someone editing the JSON file
directly, or a future code path that advances phase=DONE without
populating report_validation).

Contract: if phase is DONE, report_validation MUST be present.
emit() (or its caller) must raise so this is loud, not silent.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"


def _load_state_machine():
    spec = importlib.util.spec_from_file_location(
        "sm_under_test", str(SCRIPTS_DIR / "state_machine.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class EmitSilentDoneTests(unittest.TestCase):
    def test_emit_done_without_report_validation_raises(self) -> None:
        """If phase is DONE but report_validation is missing, emit() MUST
        raise — silently passing would let state corruption slip through."""
        sm = _load_state_machine()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = sm.StateStore(Path(tmp) / "state")
            store.set_active("corrupt-session")
            data = {
                "session_id": "corrupt-session",
                "schema_version": 3,
                "phase": "DONE",  # DONE but report_validation deliberately missing
                "params": None,
                "created_at": "2026-07-22T00:00:00+00:00",
                "updated_at": "2026-07-22T00:00:00+00:00",
                "history": [{"phase": "DONE", "at": "2026-07-22T00:00:00+00:00"}],
                # NOTE: no "report_validation" key
            }
            store.save(data)

            with self.assertRaises(Exception) as ctx:
                sm.emit(data, store)
            msg = str(ctx.exception)
            self.assertIn("DONE", msg)
            self.assertIn("report_validation", msg)


if __name__ == "__main__":
    unittest.main()

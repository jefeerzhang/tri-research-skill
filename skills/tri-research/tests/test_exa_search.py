"""Regression tests for exa_search.py import robustness.

Bug: exa_search.py has a top-level `import exa_py`. On machines without
the exa-py package, EVERY subcommand — including `check`, whose whole
purpose is to report availability — dies with an ImportError traceback
instead of emitting the documented JSON `{"available": false}` contract.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "exa_search.py"


def _load_with_exa_py_blocked():
    saved = sys.modules.get("exa_py", "ABSENT")
    sys.modules["exa_py"] = None  # makes `import exa_py` raise ImportError
    try:
        spec = importlib.util.spec_from_file_location("exa_search_blocked", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved == "ABSENT":
            sys.modules.pop("exa_py", None)
        else:
            sys.modules["exa_py"] = saved


class ExaSearchImportTests(unittest.TestCase):
    def test_module_loads_without_exa_py_installed(self) -> None:
        mod = _load_with_exa_py_blocked()  # must not raise ImportError
        self.assertIsNotNone(mod)

    def test_check_without_exa_py_reports_unavailable_json(self) -> None:
        mod = _load_with_exa_py_blocked()
        buf = io.StringIO()
        with redirect_stdout(buf):
            mod.cmd_check()
        out = json.loads(buf.getvalue())
        self.assertFalse(out["available"])


if __name__ == "__main__":
    unittest.main()

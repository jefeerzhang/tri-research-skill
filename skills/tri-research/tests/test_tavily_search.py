"""Regression tests for tavily_search.py import robustness.

Bug: tavily_search.py has a top-level `from tavily import TavilyClient`. On
machines without the tavily-python package, EVERY subcommand — including
`check`, whose whole purpose is to report availability — dies with an
ImportError traceback instead of emitting the documented JSON
`{"available": false}` contract.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "tavily_search.py"


def _load_with_tavily_blocked():
    saved = sys.modules.get("tavily", "ABSENT")
    sys.modules["tavily"] = None  # makes `from tavily import TavilyClient` raise ImportError
    try:
        spec = importlib.util.spec_from_file_location("tavily_search_blocked", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved == "ABSENT":
            sys.modules.pop("tavily", None)
        else:
            sys.modules["tavily"] = saved


class TavilySearchImportTests(unittest.TestCase):
    def test_module_loads_without_tavily_installed(self) -> None:
        mod = _load_with_tavily_blocked()  # must not raise ImportError
        self.assertIsNotNone(mod)

    def test_check_without_tavily_reports_unavailable_json(self) -> None:
        mod = _load_with_tavily_blocked()
        buf = io.StringIO()
        with redirect_stdout(buf):
            mod.cmd_check()
        out = json.loads(buf.getvalue())
        self.assertFalse(out["available"])


if __name__ == "__main__":
    unittest.main()

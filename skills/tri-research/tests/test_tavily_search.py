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
    saved_tavily = sys.modules.get("tavily", "ABSENT")
    saved_backends = sys.modules.get("search_backends")
    saved_search_cli = sys.modules.get("_search_cli")
    # Force re-import of search_backends so its `from tavily import TavilyClient`
    # Try block sees the blocked sys.modules["tavily"].
    for _k in ("search_backends", "_search_cli"):
        sys.modules.pop(_k, None)
    sys.modules["tavily"] = None  # makes `from tavily import TavilyClient` raise ImportError
    try:
        spec = importlib.util.spec_from_file_location("tavily_search_blocked", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved_tavily == "ABSENT":
            sys.modules.pop("tavily", None)
        else:
            sys.modules["tavily"] = saved_tavily
        # Restore original modules if they existed — next import will reload
        # normally; do not leave the blocked variants in sys.modules.
        for _k in ("search_backends", "_search_cli"):
            sys.modules.pop(_k, None)
        if saved_backends is not None:
            sys.modules["search_backends"] = saved_backends
        if saved_search_cli is not None:
            sys.modules["_search_cli"] = saved_search_cli


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

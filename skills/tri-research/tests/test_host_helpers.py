"""Consolidation gate for cross-script host helpers (candidate 5).

The proxy-clear tuple must exist exactly once — in `_search_cli` (the
mechanism module; registry is policy, per its header comment). A second
hand-copied tuple means `--no-proxy` silently stops working for whichever
command missed the edit — the same silent-drift class ADR-0002 killed for
check/error discipline.

The `sys.path` bootstrap ritual is deliberately NOT consolidated here:
each copy guards its own direct-script invocation (`python scripts/x.py`),
and a shared bootstrap module would itself need the path it exists to
provide. Only a packaging refactor (ADR-0004's deferred item) removes it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

TRI_SCRIPTS = Path(__file__).parents[1] / "scripts"
SERPAPI_SCRIPTS = Path(__file__).parents[2] / "serpapi" / "scripts"

PROXY_TUPLE = '"HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"'


class ProxyClearConsolidationTests(unittest.TestCase):
    def test_proxy_tuple_defined_once_in_mechanism_module(self) -> None:
        source = (TRI_SCRIPTS / "_search_cli.py").read_text(encoding="utf-8")
        self.assertEqual(
            source.count(PROXY_TUPLE),
            1,
            "the proxy env tuple must have exactly one home: _search_cli.clear_proxy_vars",
        )

    def test_no_script_reimplements_proxy_clear(self) -> None:
        """Enumerate every script so a future file can't dodge the gate."""
        for script_dir in (TRI_SCRIPTS, SERPAPI_SCRIPTS):
            for path in sorted(script_dir.glob("*.py")):
                if path.name == "_search_cli.py":
                    continue  # the single home, asserted separately
                self.assertNotIn(
                    PROXY_TUPLE,
                    path.read_text(encoding="utf-8"),
                    f"{path.name} must call _search_cli.clear_proxy_vars instead of hand-copying the tuple",
                )


if __name__ == "__main__":
    unittest.main()

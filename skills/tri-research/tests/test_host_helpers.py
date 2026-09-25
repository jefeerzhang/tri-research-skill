"""Consolidation gates for cross-script host helpers (candidates 5 / E / F).

Three rules, one shape each — all of them source gates, because the failure
they prevent is invisible at runtime: a second copy keeps working until the
day someone edits only one of them.

1. The proxy-clear tuple lives once, in `_search_cli` (the mechanism module;
   registry is policy, per its header comment). A second hand-copied tuple
   means `--no-proxy` silently stops working for whichever command missed
   the edit — the same silent-drift class ADR-0002 killed for check/error
   discipline.
2. The client-setup sequence (SDK present -> key -> build) lives once, in
   `Backend.client()`. Eight copies of it drifted before the consolidation:
   each new command path re-decided what "unavailable" means.
3. The result truncation limits live once. Two lanes with their own numbers
   made the same result read differently depending on who fetched it.

The `sys.path` bootstrap ritual for *same-skill* scripts is still not
consolidated here: each copy guards its own direct-script invocation
(``python scripts/x.py``). Cross-skill serpapi → ``_search_cli`` now goes
through ``tri_research_runtime`` (ADR-0015); remaining sibling ``scripts/``
is only for Evidence Ledger / Registry.
"""

from __future__ import annotations

import unittest
from pathlib import Path

TRI_SCRIPTS = Path(__file__).parents[1] / "scripts"
TRI_RUNTIME = Path(__file__).parents[1] / "src" / "tri_research_runtime"
SERPAPI_SCRIPTS = Path(__file__).parents[2] / "serpapi" / "scripts"

PROXY_TUPLE = '"HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"'
MECHANISM_MODULE = TRI_RUNTIME / "search_cli.py"


def _script_sources() -> list[tuple[str, str]]:
    """(filename, source) for every script in both skills plus the runtime pkg."""
    sources: list[tuple[str, str]] = []
    for script_dir in (TRI_SCRIPTS, SERPAPI_SCRIPTS, TRI_RUNTIME):
        for path in sorted(script_dir.glob("*.py")):
            sources.append((path.name, path.read_text(encoding="utf-8")))
    return sources


class ProxyClearConsolidationTests(unittest.TestCase):
    def test_proxy_tuple_defined_once_in_mechanism_module(self) -> None:
        source = MECHANISM_MODULE.read_text(encoding="utf-8")
        self.assertEqual(
            source.count(PROXY_TUPLE),
            1,
            "the proxy env tuple must have exactly one home: search_cli.clear_proxy_vars",
        )

    def test_no_script_reimplements_proxy_clear(self) -> None:
        """Enumerate every script so a future file can't dodge the gate."""
        for name, source in _script_sources():
            if name == MECHANISM_MODULE.name:
                continue  # the single home, asserted separately
            self.assertNotIn(
                PROXY_TUPLE,
                source,
                f"{name} must call _search_cli.clear_proxy_vars instead of hand-copying the tuple",
            )


class ClientBootstrapConsolidationTests(unittest.TestCase):
    """`Backend.client()` is the only place that assembles an SDK client."""

    # The two decisions of the setup sequence, spelled the way Backend.client()
    # spells them. A second copy would let one lane forget, say, the SDK check
    # — and ADR-0002's whole point is that the order is load bearing.
    BOOTSTRAP_MARKERS = ("self.client_factory(", "self.sdk is None")
    # Reaching for a factory through a *variable* means the caller assembled
    # the client itself — the exact shape Backend.client() exists to own.
    FORBIDDEN_MARKERS = ("backend.client_factory(", "spec.backend.client_factory(")

    def test_setup_sequence_lives_in_the_mechanism_module(self) -> None:
        source = MECHANISM_MODULE.read_text(encoding="utf-8")
        for marker in self.BOOTSTRAP_MARKERS:
            self.assertEqual(
                source.count(marker),
                1,
                f"{marker!r} must appear exactly once — inside Backend.client()/api_key()",
            )

    def test_no_script_builds_a_client_by_hand(self) -> None:
        for name, source in _script_sources():
            if name == MECHANISM_MODULE.name:
                markers = self.FORBIDDEN_MARKERS  # the home itself may use self.*
            else:
                markers = (*self.BOOTSTRAP_MARKERS, *self.FORBIDDEN_MARKERS)
            for marker in markers:
                self.assertNotIn(
                    marker,
                    source,
                    f"{name} must call Backend.client(); {marker!r} is a hand-copied setup",
                )


class ResultTruncationConsolidationTests(unittest.TestCase):
    """Named limits for search lanes and managed extras (ADR-0008 / ADR-0015)."""

    TRUNCATION_DECLS = (
        "def truncate(",
        "\nSNIPPET_LIMIT = ",
        "\nCONTENT_LIMIT = ",
        "\nCITATION_TEXT_LIMIT = ",
        "\nEXTRACT_CONTENT_LIMIT = ",
    )
    # Every script is in scope: a hand-written width anywhere is the drift this
    # gate exists to catch, so there is no lane allow-list to keep current.
    RESULT_FIELD_SLICES = ("[:500]", "[:5000]", "[:1000]", "[:20000]")

    def test_limits_are_declared_once_in_the_mechanism_module(self) -> None:
        source = MECHANISM_MODULE.read_text(encoding="utf-8")
        for marker in self.TRUNCATION_DECLS:
            self.assertEqual(
                source.count(marker),
                1,
                f"{marker!r} must have exactly one home: search_cli (the limits are shared policy)",
            )

    def test_no_script_recomputes_the_limits_by_hand(self) -> None:
        for name, source in _script_sources():
            if name == MECHANISM_MODULE.name:
                continue  # the home is where truncate() lives, by definition
            for literal in self.RESULT_FIELD_SLICES:
                self.assertNotIn(
                    literal,
                    source,
                    f"{name} must call truncate(value, LIMIT) instead of hard-coding {literal}",
                )


if __name__ == "__main__":
    unittest.main()

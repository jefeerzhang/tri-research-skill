"""Consumption gate for the global --no-proxy flag in the CLI skeleton.

Companion to tests/test_host_helpers.py, which pins that the proxy-clear
tuple is DEFINED exactly once (clear_proxy_vars). That gate cannot see a
command branch that forgets to CALL the cleaner — exactly how `check`
silently ignored --no-proxy until the Unreleased fix. This gate scans
_search_cli statically: the wrapper exists exactly once, and every command
branch that touches the network consumes it BEFORE the network call.

Registry.check is out of scope: it takes an explicit `no_proxy` bool
parameter (programmatic seam, no argparse), not the global flag.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SEARCH_CLI = Path(__file__).parents[1] / "scripts" / "_search_cli.py"

# Command branches that go to the network. Managed extra commands inherit
# their consumption via run_managed_command; search / batch_search consume
# at the top of their handler functions; check consumes in run()'s dispatch
# branch. Anchors are chosen so docstrings mentioning `search` cannot shift
# the slice.
CONSUMERS = {
    "check": 'if args.command == "check":',
    "search": "def search(backend",
    "batch_search": "def batch_search(backend",
    "run_managed_command": "def run_managed_command(",
}

# Branches whose consumption must come at the top of the branch body.
TOP_OF_BRANCH = {"search", "batch_search", "run_managed_command"}


def _consumer_section(source: str, name: str) -> str:
    """Slice the source from the consumer's anchor to the next anchor/def.

    `def ` as terminator stops run()'s body before the next function, so a
    stray call outside the branch cannot satisfy the gate.
    """
    start = source.index(CONSUMERS[name])
    end = len(source)
    for needle in (*CONSUMERS.values(), "def "):
        candidate = source.find(needle, start + len(CONSUMERS[name]))
        if candidate != -1:
            end = min(end, candidate)
    return source[start:end]


class NoProxyConsumptionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = SEARCH_CLI.read_text(encoding="utf-8")

    def test_caller_defined_exactly_once(self) -> None:
        """One definition + no duplicate calls anywhere in the module."""
        definitions = len(re.findall(r"def _maybe_clear_proxy\(", self.source))
        calls = len(re.findall(r"_maybe_clear_proxy\(args\)", self.source))
        self.assertEqual(definitions, 1, "clear_proxy_vars wrapper drifted: expected exactly one definition")
        self.assertEqual(
            calls,
            len(CONSUMERS),
            f"one _maybe_clear_proxy(args) call per network command branch — expected {len(CONSUMERS)}, found {calls}",
        )

    def test_each_branch_consumes_before_its_network_call(self) -> None:
        for name in CONSUMERS:
            section = _consumer_section(self.source, name)
            call_pos = section.find("_maybe_clear_proxy(args)")
            self.assertNotEqual(
                call_pos,
                -1,
                f"{name} must consume the global --no-proxy flag via _maybe_clear_proxy(args)",
            )
            if name in TOP_OF_BRANCH:
                self.assertLess(
                    call_pos,
                    section.index("invoke("),
                    f"{name} must clear proxy env vars before the first invoke()",
                )


if __name__ == "__main__":
    unittest.main()

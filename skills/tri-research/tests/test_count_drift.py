"""Regression test: catch drift between claimed test counts and reality.

Background
----------
Several documents (e.g. ``examples/DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md``)
historically hard-coded the test count as ``35/35``. As of v6.5.0 the real
unittest discover reports 111 (tri-research) + 10 (serpapi) = 121. This file
pins the following rules so a future contributor who adds/removes a test
cannot silently let the documents lie:

1. ``unittest discover`` must report at least ``MIN_TRI_RESEARCH`` tests under
   ``skills/tri-research/tests``. Threshold leaves headroom for refactors but
   fails loudly if someone deletes the bulk of the suite.
2. The same for ``skills/serpapi/tests`` (lower threshold; that suite is small).
3. The example report ``examples/DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md``
   must NOT contain a stale ``\b35/35\b`` substring. If the count is ever
   quoted there again, this test fails (forcing an explicit update).
4. The CHANGELOG's ``[Unreleased]`` section, if present, must NOT claim a
   specific stale count without justification.

Implementation note
-------------------
``_count_tests`` spawns a child ``unittest discover`` process. If we called
it from every ``test_*`` method, the suite would re-discover itself once per
test, multiplying cost by N. We instead cache the counts once in
``setUpClass`` and let each ``test_*`` method read the cached value.

Run isolated: ``python -m unittest skills.tri-research.tests.test_count_drift -v``
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TRI_RESEARCH_TESTS = REPO_ROOT / "skills" / "tri-research" / "tests"
SERPAPI_TESTS = REPO_ROOT / "skills" / "serpapi" / "tests"
LABOR_EXAMPLE = (
    REPO_ROOT
    / "examples"
    / "DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md"
)
CHANGELOG = REPO_ROOT / "skills" / "tri-research" / "CHANGELOG.md"

# As of v6.5.0: 111 tri-research + 10 serpapi = 121. Keep generous headroom
# so a minor change does not break the gate, but block silent mass deletion.
MIN_TRI_RESEARCH = 100
MIN_SERPAPI = 5


def _count_tests(tests_dir: Path) -> int:
    """Statically count test cases without actually running them.

    We use ``loader.discover(...)`` + ``suite.countTestCases()`` in a child
    interpreter so we never invoke ``TestCase`` bodies. Running the tests in
    a child would re-enter ``setUpClass`` → re-spawn another child → infinite
    recursion. Counting without running is O(files · classes) and finishes
    in well under a second.
    """
    quoted = str(tests_dir).replace("\\", "\\\\").replace("'", "\\'")
    snippet = (
        "import sys, unittest; "
        f"sys.path.insert(0, r'{REPO_ROOT.as_posix()}'); "
        f"loader = unittest.TestLoader(); "
        f"suite = loader.discover(r'{quoted}'); "
        "print(suite.countTestCases())"
    )
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    match = re.search(r"\b(\d+)\b", output)
    if match is None or proc.returncode != 0:
        raise AssertionError(
            f"countTestCases() failed for {tests_dir} (rc={proc.returncode}).\n"
            f"--- stdout ---\n{proc.stdout[-500:]}\n"
            f"--- stderr ---\n{proc.stderr[-500:]}"
        )
    return int(match.group(1))


class TestCountDriftTests(unittest.TestCase):
    # Populated by setUpClass below; tests read these to avoid re-spawning
    # a full unittest discover on every assertion.
    tri_research_count: int = -1
    serpapi_count: int = -1

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.tri_research_count = _count_tests(TRI_RESEARCH_TESTS)
        cls.serpapi_count = _count_tests(SERPAPI_TESTS)

    def test_tri_research_test_count_meets_minimum(self) -> None:
        self.assertGreaterEqual(
            self.tri_research_count,
            MIN_TRI_RESEARCH,
            f"tri-research tests dropped to {self.tri_research_count}; "
            f"expected ≥ {MIN_TRI_RESEARCH}. If intentional, update "
            f"MIN_TRI_RESEARCH in tests/test_count_drift.py.",
        )

    def test_serpapi_test_count_meets_minimum(self) -> None:
        self.assertGreaterEqual(
            self.serpapi_count,
            MIN_SERPAPI,
            f"serpapi tests dropped to {self.serpapi_count}; "
            f"expected ≥ {MIN_SERPAPI}.",
        )

    def test_labor_example_does_not_quote_stale_35_35(self) -> None:
        text = LABOR_EXAMPLE.read_text(encoding="utf-8")
        # \b35/35\b catches "35/35" but not "135/135" or "35/350".
        self.assertNotRegex(
            text,
            r"\b35/35\b",
            "examples/...劳动分配...md still contains the stale '35/35' "
            "test count. Update it to the current discover output "
            "(`python -m unittest discover -s skills/tri-research/tests` "
            "+ serpapi/tests) so the document reflects reality.",
        )

    def test_changelog_unreleased_does_not_quote_stale_35_35(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        # Pin only the [Unreleased] block, not historical releases.
        match = re.search(
            r"^## \[Unreleased\]\s*$\n(.+?)(?=^## \[|\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        if match is None:
            # No Unreleased block — that is fine.
            return
        unreleased = match.group(1)
        self.assertNotRegex(
            unreleased,
            r"\b35/35\b",
            "CHANGELOG [Unreleased] quotes stale '35/35'. Remove the hard "
            "count from prose — the live number lives in "
            "tests/test_count_drift.py.",
        )


if __name__ == "__main__":
    unittest.main()
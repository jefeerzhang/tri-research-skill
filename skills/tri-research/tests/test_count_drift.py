"""Regression test: catch drift between claimed test counts and reality.

Background
----------
Documents historically hard-coded the test count (``35/35``, then ``121/121``).
The live number changes whenever a test is added, so a hard-coded number in a
**live** document is a lie waiting to happen. This file pins four rules so a
future contributor cannot silently let the documents lie:

1. ``unittest discover`` must report at least ``MIN_TRI_RESEARCH`` tests under
   ``skills/tri-research/tests``. Threshold leaves headroom for refactors but
   fails loudly if someone deletes the bulk of the suite.
2. The same for ``skills/serpapi/tests`` (lower threshold; that suite is small).
3. **Live documents must not hard-code a test count** (``LIVE_DOCS`` below).
   The count has exactly one dynamic owner: ``unittest discover``.
4. The live surface must point at that dynamic owner, so a reader has somewhere
   to look instead of trusting prose.

A dated *record* (``examples/``, past CHANGELOG releases) may quote the number it
saw — that is history, and rewriting it would falsify the record. The claimed
number in a record is therefore deliberately NOT compared against today's
discover output. What this file prevents is a **live** document claiming a
number that no longer holds.

Implementation note
-------------------
``_count_tests`` spawns a child ``unittest discover`` process. If we called it
from every ``test_*`` method, the suite would re-discover itself once per test,
multiplying cost by N. We instead cache the counts once in ``setUpClass`` and
let each ``test_*`` method read the cached value.

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
LABOR_EXAMPLE = REPO_ROOT / "examples" / "DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md"
CHANGELOG = REPO_ROOT / "skills" / "tri-research" / "CHANGELOG.md"

# As of v6.5.0: 111 tri-research + 10 serpapi = 121. Keep generous headroom
# so a minor change does not break the gate, but block silent mass deletion.
MIN_TRI_RESEARCH = 100
MIN_SERPAPI = 5

# 「现在有几个测试」的活文档面。计数只许有一个动态真源（unittest discover），
# 所以这些文件里不得出现硬编码的数字。清单是显式的，与
# test_skill_contract.ROSTER_BEARING_FILES 同一风格：记录（examples/、历史
# CHANGELOG 条目）不在其内，回填历史不是本棘轮的职责。
LIVE_DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "CONTEXT.md",
    REPO_ROOT / "skills" / "tri-research" / "SKILL.md",
    REPO_ROOT / "skills" / "tri-research" / "README.md",
    REPO_ROOT / "skills" / "tri-research" / "test-prompts.json",
    REPO_ROOT / "skills" / "tri-research" / "references" / "report-format.md",
    REPO_ROOT / "skills" / "tri-research" / "references" / "runtime-adapters.md",
    REPO_ROOT / "skills" / "research-subagent" / "SKILL.md",
    REPO_ROOT / "skills" / "citations" / "SKILL.md",
    REPO_ROOT / ".claude-plugin" / "marketplace.json",
)

# 「硬编码了一个测试计数」的形态。刻意收窄，免得把压力测试（stress test）、
# 日期（2022/02）、层级（1/2/3）当命中：
#   - 比率后紧跟「通过 / passed」
#   - 「通过 / passed」后紧跟比率
#   - N+M=K 求和
#   - 数字紧贴 unit tests / tests
# 中文「测试」单独出现噪音过大（压力测试、测试试点、试测），故不列入。
COUNT_CLAIM_PATTERNS = (
    re.compile(r"\b\d{2,4}\s*/\s*\d{2,4}\b[^\n]{0,20}(?:通过|passed)"),
    re.compile(r"(?:通过|passed)[^\n]{0,10}\b\d{2,4}\s*/\s*\d{2,4}\b"),
    re.compile(r"\b\d{1,4}\s*\+\s*\d{1,4}\s*=\s*\d{1,4}\b"),
    re.compile(r"\b\d{2,4}\s*(?:个)?\s*(?:unit\s*tests?|tests?)\b", re.IGNORECASE),
)

# 计数真源的指针：活文档必须指向它，而不是自己记一个数。
TRUTH_POINTER = "unittest discover"

# 带版本 / 日期限定 = 读起来是历史记录，不是当下事实。
HISTORY_QUALIFIER = re.compile(r"v\d+\.\d+\.\d+|\b20\d{2}-\d{2}-\d{2}\b|\b20\d{2}\b")


def _count_claims(text: str) -> list[str]:
    """Every hard-coded test-count claim in ``text``, in document order."""
    hits: list[tuple[int, str]] = []
    for pattern in COUNT_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            hits.append((match.start(), match.group(0).strip()))
    return [claim for _, claim in sorted(hits)]


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
            f"serpapi tests dropped to {self.serpapi_count}; expected ≥ {MIN_SERPAPI}.",
        )

    def test_live_docs_do_not_hardcode_a_test_count(self) -> None:
        """活文档不得硬编码计数（候选 8：把「禁止过期数字」写成通则）。

        原先只禁示例文档里的 ``35/35`` 一个字面量；一个退役数字被禁住，下一个
        数字照样能写进 SKILL / README。现在改成通则：活文档面里出现任何形态的
        计数即红。计数只有一个动态真源 —— ``unittest discover``。
        """
        offenders: list[str] = []
        for path in LIVE_DOCS:
            self.assertTrue(path.exists(), f"LIVE_DOCS 登记了不存在的文件: {path}")
            claims = _count_claims(path.read_text(encoding="utf-8"))
            if claims:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {claims}")
        self.assertEqual(
            offenders,
            [],
            "活文档硬编码了测试计数；请删除数字并指向 `python -m unittest discover`（动态真源）:\n  "
            + "\n  ".join(offenders),
        )

    def test_live_surface_points_at_the_dynamic_count_owner(self) -> None:
        """删了数字之后，读者必须有地方查到真值 —— 指针本身也是契约。"""
        readme = (REPO_ROOT / "skills" / "tri-research" / "README.md").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover", readme, "README 缺少可运行的测试命令")
        self.assertIn(TRUTH_POINTER, readme, "README 未声明「测试数量以 discover 为准」")

    def test_changelog_unreleased_does_not_hardcode_a_test_count(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        # Pin only the [Unreleased] block, not historical releases: a past release
        # entry quoting its own count is a record, and rewriting it would lie.
        match = re.search(
            r"^## \[Unreleased\]\s*$\n(.+?)(?=^## \[|\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        if match is None:
            return  # No Unreleased block — that is fine.
        claims = _count_claims(match.group(1))
        self.assertEqual(
            claims,
            [],
            f"CHANGELOG [Unreleased] 硬编码了计数 {claims}; 删除数字，活数字只有 unittest discover 一个家。",
        )

    def test_historical_counts_are_qualified_as_history(self) -> None:
        """历史记录可以引用它当时的计数，但整份记录必须带版本 / 日期限定。

        否则读者会把「v6.5.0 时的 121」误读成「现在就是 121」。本测试**不**把
        记录里的数字与今日 discover 结果比对 —— 记录在写下时为真，改写即伪造。
        """
        text = LABOR_EXAMPLE.read_text(encoding="utf-8")
        if not _count_claims(text):
            self.skipTest("示例报告已不再引用计数")
        self.assertRegex(
            text,
            HISTORY_QUALIFIER,
            "示例报告引用了计数但没有任何版本 / 日期限定，会被误读成当下事实",
        )


if __name__ == "__main__":
    unittest.main()

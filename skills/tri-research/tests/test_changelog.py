"""Regression tests for CHANGELOG.md structural invariants.

The 6.0.0 release entry was authored with two consecutive Added/Fixed/Changed
blocks (lines 8-25 and 31-44), which doubles several items including the
Tavily v5 and SciVerse Python-SDK changes. This test pins the rule:
each (Added/Fixed/Changed/Removed/Verified) heading should appear at most
once under the topmost release heading.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

CHANGELOG = Path(__file__).parents[1] / "CHANGELOG.md"


class ChangelogSectionUniquenessTests(unittest.TestCase):
    def test_no_repeated_subheadings_in_latest_release(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        # Find the most recent (topmost) release heading like "## [6.0.0] - DATE"
        match = re.search(r"^##\s+\[[^\]]+\]\s+-\s+\d{4}-\d{2}-\d{2}\s*$",
                          text, flags=re.MULTILINE)
        self.assertIsNotNone(match, "no release heading found in CHANGELOG")
        start = match.end()
        # Next release heading marks the end of the latest block
        next_release = re.search(r"^##\s+\[[^\]]+\]\s+-\s+\d{4}-\d{2}-\d{2}\s*$",
                                  text[start:], flags=re.MULTILINE)
        end = start + next_release.start() if next_release else len(text)
        latest = text[start:end]

        # Subheadings like "### Added", "### Fixed", "### Changed" within block
        subheadings = re.findall(r"^###\s+([A-Za-z]+)\s*$", latest,
                                 flags=re.MULTILINE)
        seen: dict[str, int] = {}
        for name in subheadings:
            seen[name] = seen.get(name, 0) + 1
        duplicates = sorted(name for name, count in seen.items() if count > 1)
        self.assertEqual(
            duplicates, [],
            msg=(
                f"Latest release entry has repeated ### subheadings: {duplicates}.\n"
                f"Each (Added/Fixed/Changed/Removed/Verified) should appear only once."
            ),
        )


if __name__ == "__main__":
    unittest.main()

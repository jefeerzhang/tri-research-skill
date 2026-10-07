"""Report source floor shared by the tri-research CLIs (candidate 5).

This module owns exactly two facts, plus one explicit facade:

1. ``MIN_REPORT_SOURCES`` — the floor a Research Session's ``min_sources`` must
   clear (CONTEXT.md: Report Validation). ``state_machine.py`` and
   ``validate_report.py`` both read it here, so the two thresholds cannot be
   raised independently — which is what used to happen before this module.
2. ``source_threshold`` — the argparse type built on that floor.
3. ``StateError`` — a re-export facade so callers need not carry the package
   path (ADR-0015). The class itself lives in ``tri_research_runtime.errors``.

Not here, deliberately:

- Timestamps. ``now_iso`` moved to ``tri_research_runtime.clock`` with the other
  shared primitives; a module named after the report floor should not be the
  place you look for the clock.
- The ``src/`` sys.path bootstrap. That is ``_runtime.py``'s single job; this
  module imports it rather than repeating the three lines.
"""

from __future__ import annotations

import argparse

import _runtime  # noqa: F401  — the one home of the src/ sys.path bootstrap

from tri_research_runtime.errors import StateError  # noqa: E402, F401  — re-export (ADR-0015)

MIN_REPORT_SOURCES = 10


def source_threshold(value: str) -> int:
    """argparse type for --min-sources: must be at least MIN_REPORT_SOURCES."""
    parsed = int(value)
    if parsed < MIN_REPORT_SOURCES:
        raise argparse.ArgumentTypeError(f"至少为 {MIN_REPORT_SOURCES}")
    return parsed

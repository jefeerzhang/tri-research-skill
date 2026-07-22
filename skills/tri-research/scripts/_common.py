"""Shared constants and helpers for the tri-research scripts.

This module exists so that state_machine.py and validate_report.py
do not each define their own MIN_REPORT_SOURCES and source_threshold.
Both files import from here. Keeping a single source of truth prevents
the two implementations from drifting apart (which previously caused the
two thresholds to be set independently — a real footgun if a maintainer
ever raised one without the other).
"""
from __future__ import annotations

import argparse

MIN_REPORT_SOURCES = 10


def source_threshold(value: str) -> int:
    """argparse type for --min-sources: must be at least MIN_REPORT_SOURCES."""
    parsed = int(value)
    if parsed < MIN_REPORT_SOURCES:
        raise argparse.ArgumentTypeError(f"至少为 {MIN_REPORT_SOURCES}")
    return parsed

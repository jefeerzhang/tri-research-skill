"""Hashing primitive shared by the tri-research scripts (ADR-0015).

``sha256_bytes`` is the one digest used by the report proof and by the evidence
ledger. It lives here, beside ``clock`` and the truncation limits, so the
algorithm has an owner whose name says what it owns — it previously sat inside
``scripts/validate_report.py``, which forced the evidence ledger to import a
report-unrelated tool from the report judgment module and re-coupled the pair
that ADR-0014 had just separated.

No behaviour change: same SHA-256, same lowercase hex digest.
"""

from __future__ import annotations

import hashlib


def sha256_bytes(content: bytes) -> str:
    """Lowercase hex SHA-256 of ``content`` — the repo's one digest format."""
    return hashlib.sha256(content).hexdigest()

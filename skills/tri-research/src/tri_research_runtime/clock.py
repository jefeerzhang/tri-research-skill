"""Clock primitive shared by the tri-research scripts (ADR-0015).

``now_iso`` is the single timestamp format for state files, the evidence ledger
and the DONE proof. It lives here, beside ``errors`` and the truncation limits,
so the format has an owner whose name says what it owns — it previously rode
along inside ``scripts/_common.py``, a module whose docstring described only the
report source floor.

No behaviour change: same UTC ISO-8601, same minute precision.
"""

from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    """UTC timestamp in ISO-8601, minute precision — the repo's one format."""
    return datetime.now(timezone.utc).isoformat(timespec="minutes")

#!/usr/bin/env python3
"""Deep module for the DONE ``report_validation`` proof lifecycle.

Previously the whole proof — its schema, the report half, the ledger half,
and the build/verify orchestration — was split across three modules:

* ``validate_report`` owned the report half but *also* asserted the full
  schema (including ledger-only keys it never builds);
* ``evidence`` owned the ledger half;
* ``state_machine`` glued the halves together and sequenced verification.

That split made the proof contract leak across module boundaries: a change
to the ledger fingerprint recipe was invisible to the report module that
claimed to own the schema, so a silent drift (a false ``INTEGRITY:OK``)
became possible. This module absorbs the whole contract behind one facade:
build both halves, assert the complete schema, verify both halves, and
translate every failure into one of two markers (MISSING / MISMATCH) so
callers no longer need to know which half failed.

This is the *deepening*: the interface is narrow (``build_proof`` /
``require_complete`` / ``verify_integrity``), while the implementation
absorbs the cross-module wiring that used to live in the orchestrator.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Make sibling modules importable however this file is loaded (direct
# script execution, tests via importlib, external tooling) — same bootstrap
# as the other scripts.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from validate_report import (  # noqa: E402
    ReportMissingError,
    ReportTamperedError,
    ReportValidationError,
    validate_and_build_proof,
)
from evidence import (  # noqa: E402
    LedgerMissingError,
    LedgerTamperedError,
    evidence_path,
    ledger_fingerprint,
    verify_ledger_integrity,
)

# Full proof contract (schema v4): the report half plus the ledger half.
# This is the single source of truth for what a DONE proof must carry.
REQUIRED_PROOF_KEYS = ("path", "sha256", "min_sources", "evidence_lines", "evidence_sha256")


class ProofError(ReportValidationError):
    """Base error for the DONE proof lifecycle (callers catch this type)."""

    marker = "MISMATCH"


class ProofMissingError(ProofError):
    """The report / ledger backing a proof can no longer be read."""

    marker = "MISSING"


class ProofTamperedError(ProofError):
    """The report / ledger bytes changed after the DONE proof recorded them."""

    marker = "MISMATCH"


def build_proof(
    store: Any,
    session_id: str,
    report_path: Path,
    min_sources: int,
    *,
    expected_topic: str,
) -> dict[str, Any]:
    """Build a complete ``report_validation`` proof in one call.

    Fuses the report half (``validate_report``: path / sha256 /
    min_sources / topic / validated_at) with the ledger half
    (``evidence``: evidence_lines / evidence_sha256). Callers no longer
    merge two modules' outputs; they get the finished contract.
    """
    proof = validate_and_build_proof(report_path, min_sources, expected_topic=expected_topic)
    proof.update(ledger_fingerprint(store, session_id))
    return proof


def require_complete(proof: Any, session_id: str) -> None:
    """Assert a DONE proof carries the complete schema.

    Raises ``ProofError`` (never a bare ``KeyError`` / ``TypeError``) so a
    hand-corrupted state translates to a CLI-friendly error.
    """
    if not isinstance(proof, dict):
        raise ProofError(
            f"phase=DONE but report_validation is missing for session {session_id!r} — state file is corrupt"
        )
    missing = [key for key in REQUIRED_PROOF_KEYS if key not in proof or proof[key] in (None, "")]
    if missing:
        raise ProofError(
            f"phase=DONE but report_validation is incomplete for session "
            f"{session_id!r} (missing: {', '.join(missing)}) — state file is corrupt"
        )


def verify_integrity(proof: dict[str, Any], store: Any, session_id: str) -> str:
    """Verify both halves of a proof against their DONE fingerprints.

    Recomputes the report hash (``validate_report``) and the ledger hash
    (``evidence``) using the same raw-byte recipe used at build time, and
    returns ``"OK"`` when both match. Any mismatch or unreadable backing
    file raises ``ProofMissingError`` / ``ProofTamperedError`` (both carry a
    ``marker``), so the caller no longer needs to know which half failed.
    """
    try:
        from validate_report import verify_proof_integrity  # local to keep imports tidy

        verify_proof_integrity(proof)
    except ReportMissingError as exc:
        raise ProofMissingError(str(exc)) from exc
    except ReportTamperedError as exc:
        raise ProofTamperedError(str(exc)) from exc

    try:
        verify_ledger_integrity(proof, evidence_path(store, session_id))
    except LedgerMissingError as exc:
        raise ProofMissingError(str(exc)) from exc
    except LedgerTamperedError as exc:
        raise ProofTamperedError(str(exc)) from exc

    return "OK"


if __name__ == "__main__":
    raise SystemExit("proof.py is a library module; use state_machine.py for the CLI")

#!/usr/bin/env python3
"""简化版状态机：start（初始化）→ done（验证完成）。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

# Make sibling `validate_report` and `_common` importable regardless of how
# this file is invoked. Direct script execution (python state_machine.py)
# already prepends the script's directory to sys.path[0], but importlib-based
# loaders (e.g. `importlib.util.spec_from_file_location` used by tests and
# external tooling) do NOT. Without this injection, `from validate_report
# import validate` fails with ModuleNotFoundError on those code paths.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _common import (  # noqa: E402
    MIN_REPORT_SOURCES,
    StateError,
    now_iso,
    source_threshold,
)
from validate_report import (  # noqa: E402
    ReportMissingError,
    ReportTamperedError,
    ReportValidationError,
    require_complete_proof,
    validate_and_build_proof,
    verify_proof_integrity,
)

SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# Cross-process file locking. fcntl is POSIX-only; on Windows we fall back
# to msvcrt with a lock-file poll so LOCK_WAIT_SECONDS is honored. See
# session_lock below.
try:
    import fcntl
except ImportError:  # Windows
    import msvcrt  # type: ignore[import-not-found]

    fcntl = None  # type: ignore[assignment]

LOCK_WAIT_SECONDS = 30.0
LOCK_POLL_SECONDS = 0.1


@contextmanager
def session_lock(lock_path: Path) -> Iterator[None]:
    """Serialize read-modify-write access to a session's state file.

    Every mutating command (set_params / add_dimensions / done) takes this
    lock for the whole command. Atomic file writes (temp + os.replace) only
    prevent torn reads; they do not serialize two processes that both load,
    mutate and save — without the lock, two concurrent `done` calls on the
    same session silently drop each other's history entry and updated_at.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = lock_path.open("a+", encoding="utf-8")
    locked = False
    try:
        if fcntl is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            locked = True
        else:  # Windows: msvcrt.LK_LOCK retries ~10s then raises bare OSError;
            # poll with LK_NBLCK instead so LOCK_WAIT_SECONDS is honored
            # and timeouts surface as StateError (ERROR: line, exit 1),
            # not a traceback. Only unlock if we actually acquired.
            lock_handle.seek(0)
            deadline = datetime.now().timestamp() + LOCK_WAIT_SECONDS
            while True:
                try:
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    if datetime.now().timestamp() > deadline:
                        raise StateError(f"timed out waiting for state lock: {lock_path}") from None
                    _sleep(LOCK_POLL_SECONDS)
        yield
    finally:
        try:
            if locked:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                else:
                    lock_handle.seek(0)
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            lock_handle.close()


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def default_state_dir() -> Path:
    configured = os.environ.get("TRI_RESEARCH_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(tempfile.gettempdir()) / "tri-research-state"


def validate_session_id(session_id: str) -> str:
    if not SESSION_RE.fullmatch(session_id):
        raise StateError("session id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    return session_id


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"{field} must be a non-empty string")
    return value.strip()


def validate_params(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise StateError("params must be a JSON object")
    normalized = dict(params)
    normalized["topic"] = require_text(params.get("topic"), "topic")
    min_sources = params.get("min_sources")
    if isinstance(min_sources, bool) or not isinstance(min_sources, int):
        raise StateError("min_sources must be an integer")
    if min_sources < MIN_REPORT_SOURCES:
        raise StateError(f"min_sources must be at least {MIN_REPORT_SOURCES}")
    normalized["min_sources"] = min_sources
    for field in ("keywords_zh", "keywords_en"):
        values = params.get(field)
        if not isinstance(values, list) or not values:
            raise StateError(f"{field} must be a non-empty list")
        normalized[field] = [require_text(value, field) for value in values]
    return normalized


def validate_extension(extension: Any) -> dict[str, Any]:
    if not isinstance(extension, dict):
        raise StateError("extension must be a JSON object")
    validated: dict[str, Any] = {}
    for field in ("keywords_zh", "keywords_en", "dimensions"):
        values = extension.get(field)
        if values is not None:
            if not isinstance(values, list) or not values:
                raise StateError(f"{field} must be a non-empty list when provided")
            validated[field] = [require_text(value, field) for value in values]
    if not validated:
        raise StateError("extension must include at least one of: keywords_zh, keywords_en, dimensions")
    return validated


class StateStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.active_file = self.state_dir / "active-session"

    def state_path(self, session_id: str) -> Path:
        return self.state_dir / f"{validate_session_id(session_id)}.json"

    def set_active(self, session_id: str) -> None:
        self._atomic_write_text(self.active_file, session_id + "\n")

    def clear_active(self, session_id: str | None = None) -> None:
        """Remove the active-session pointer when it refers to `session_id`.

        Called after a session transitions to DONE so that subsequent
        callers who run a read command without --session get the
        'no active session' error instead of silently receiving a
        completed session's state.

        If `session_id` is given, only clear when the pointer currently
        points at that session — completing B must not wipe an active
        pointer that still refers to A.
        """
        if not self.active_file.exists():
            return
        if session_id is not None:
            try:
                current = self.active_file.read_text(encoding="utf-8").strip()
            except OSError:
                return
            if current != session_id:
                return
        try:
            self.active_file.unlink()
        except FileNotFoundError:
            pass  # already gone — no-op

    def start_session(self, session_id: str | None = None) -> dict[str, Any]:
        """Start a new session and make it the active session."""
        if session_id is None:
            # Second granularity: two researches opened within the same
            # minute used to collide on "session already exists".
            session_id = datetime.now().strftime("research-%Y%m%d-%H%M%S")
        session_id = validate_session_id(session_id)
        with self.write_lock(session_id):
            path = self.state_path(session_id)
            if path.exists():
                raise StateError(f"session already exists: {session_id}")
            # Same guard for a stale ledger: someone who "reset" a session
            # by deleting the state JSON must not silently inherit the old
            # evidence — those URLs would pass the done audit as if they
            # had been seen by THIS session.
            evidence_candidate = self.state_dir / f"{session_id}.evidence.jsonl"
            if evidence_candidate.exists():
                raise StateError(
                    f"evidence ledger already exists for session {session_id} (delete it or use another session id)"
                )
            timestamp = now_iso()
            data = {
                "session_id": session_id,
                "schema_version": 4,
                "phase": "STARTED",
                "params": None,
                "created_at": timestamp,
                "updated_at": timestamp,
                "history": [{"phase": "STARTED", "at": timestamp}],
            }
            self.save(data)
            self.set_active(session_id)
        return data

    def set_params(self, session_id: str, params: dict[str, Any]) -> dict[str, Any]:
        """Set immutable research parameters for a STARTED session."""
        session_id = validate_session_id(session_id)
        with self.write_lock(session_id):
            data = self.load(session_id)
            if data["phase"] != "STARTED":
                raise StateError("parameters can only be set in STARTED phase")
            if data.get("params") is not None:
                raise StateError("parameters already set and immutable")
            normalized = validate_params(params)
            data["params"] = normalized
            data["updated_at"] = now_iso()
            self.save(data)
        return data

    def extend(self, session_id: str, extension: dict[str, Any]) -> dict[str, Any]:
        """Append dimensions/keywords to a session, preserving prior work."""
        session_id = validate_session_id(session_id)
        with self.write_lock(session_id):
            data = self.load(session_id)
            params = data.get("params")
            if params is None:
                raise StateError("parameters not set; run set_params first")
            normalized = validate_extension(extension)
            was_done = data["phase"] == "DONE"
            for field in ("keywords_zh", "keywords_en", "dimensions"):
                added = normalized.get(field)
                if added:
                    existing = params.setdefault(field, [])
                    for item in added:
                        if item not in existing:
                            existing.append(item)
            data["updated_at"] = now_iso()
            extend_phase = "EXTENDED" if was_done else data["phase"]
            data["history"].append({"phase": extend_phase, "at": now_iso(), "extension": normalized})
            if was_done:
                # Stale report_validation is no longer valid after extension.
                data.pop("report_validation", None)
                # Reset phase so the workflow can continue.
                data["phase"] = "EXTENDED"
                # Re-set active session pointer since done cleared it.
                self.set_active(session_id)
            self.save(data)
        return data

    def complete(
        self,
        session_id: str,
        report_path: Path,
        min_sources: int | None = None,
    ) -> dict[str, Any]:
        """Validate a report, transition the session to DONE, and clear active.

        `min_sources` is an optional CLI-level override check; when provided it
        must match the confirmed ``params.min_sources``.
        """
        session_id = validate_session_id(session_id)
        # Expand `~/…` once, at the boundary: validate_and_build_proof already
        # expanduser()s internally, but the Evidence Audit below reads the
        # report through report_reference_urls, which does not. Passing the raw
        # `~/…` made validation succeed while audit died on "cannot read
        # report" — the documented default output path (~/tri-research-reports/)
        # tripped this on every done.
        report_path = Path(report_path).expanduser()
        with self.write_lock(session_id):
            data = self.load(session_id)
            if data["phase"] == "DONE":
                raise StateError("session already completed")
            params = data.get("params")
            if params is None:
                raise StateError("parameters not set; run set_params first")
            confirmed_min_sources = params["min_sources"]
            if min_sources is not None and min_sources != confirmed_min_sources:
                raise StateError(f"--min-sources does not match confirmed min_sources ({confirmed_min_sources})")
            try:
                proof = validate_and_build_proof(
                    report_path,
                    confirmed_min_sources,
                    expected_topic=params["topic"],
                )
            except ReportValidationError as exc:
                raise StateError(str(exc)) from exc
            # Evidence Audit hard gate: every reference URL in the report
            # must trace to the session's evidence ledger. Imported lazily:
            # evidence.py imports this module at load time, so a top-level
            # import would be circular. Runs while the write lock is held
            # but only reads the ledger — no new locking of its own.
            from evidence import audit_report, format_untraced, ledger_fingerprint

            untraced, total = audit_report(self, session_id, report_path)
            if untraced:
                raise StateError(
                    f"evidence audit failed: {len(untraced)}/{total} reference URL(s) untraced: "
                    f"{format_untraced(untraced)}"
                )
            # Ledger snapshot fingerprint: part of the proof, so `check`
            # can catch post-DONE ledger edits (e.g. backdated rows).
            proof.update(ledger_fingerprint(self, session_id))
            timestamp = proof["validated_at"]
            data["phase"] = "DONE"
            data["updated_at"] = timestamp
            data["report_validation"] = proof
            data["history"].append({"phase": "DONE", "at": timestamp})
            self.save(data)
            # Clear the active-session pointer only if it still points at this
            # session. Completing B must not wipe an active pointer for A.
            self.clear_active(session_id)
        return data

    def resolve_session(self, requested: str | None) -> str:
        if requested:
            return validate_session_id(requested)
        if not self.active_file.exists():
            raise StateError("no active session; run start first or pass --session")
        return validate_session_id(self.active_file.read_text(encoding="utf-8").strip())

    def load(self, session_id: str) -> dict[str, Any]:
        path = self.state_path(session_id)
        if not path.exists():
            raise StateError(f"session does not exist: {session_id}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"invalid state file: {exc}") from exc
        return data

    @contextmanager
    def write_lock(self, session_id: str) -> Iterator[None]:
        """Cross-process lock guarding a session's read-modify-write.

        Advisory locks (fcntl on POSIX, msvcrt on Windows) are authoritative;
        the lock file persists on disk as an empty marker and is deliberately
        NOT unlinked (deleting a locked file lets a third process lock the
        orphaned inode — a classic race).
        """
        with session_lock(self.state_path(session_id).with_suffix(".lock")):
            yield

    def save(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        self._atomic_write_text(self.state_path(data["session_id"]), payload)

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        # The temp name must be unique per process. Two processes writing the
        # same path concurrently (e.g. two `start` commands for DIFFERENT
        # sessions both updating the shared `active-session` pointer — the
        # per-session lock does not cover that file) used to collide on the
        # deterministic `<path>.tmp`: one process replaced it while the other
        # still had it open (PermissionError on Windows) or was about to
        # replace it (FileNotFoundError on POSIX). A per-pid temp name keeps
        # every writer's temp file private; os.replace onto the destination
        # stays atomic.
        temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temp_path.write_text(content, encoding="utf-8")
        # On Windows, MoveFileEx (which backs os.replace) transiently fails
        # with ACCESS_DENIED when several processes replace the SAME target
        # at the same moment, or when a reader (clear_active /
        # resolve_session) holds the destination open without delete
        # sharing. The window is milliseconds — retry briefly, then give up.
        attempts = 10
        for attempt in range(attempts):
            try:
                os.replace(temp_path, path)
                return
            except PermissionError:
                if attempt + 1 >= attempts:
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
                    raise StateError(f"could not write {path}: file is busy")
                _sleep(0.05 * (attempt + 1))


def emit(data: dict[str, Any], store: StateStore) -> None:
    phase = data["phase"]
    print(f"STATE:{phase}")
    print(f"SESSION:{data['session_id']}")
    print(f"FILE:{store.state_path(data['session_id'])}")
    if phase == "DONE":
        # A DONE phase MUST carry a complete report_validation proof.
        # Missing or partial proof means the state file is corrupt (hand
        # edit, or a code path that advanced to DONE without populating
        # all fields). Delegate the assertion to the report-validation
        # module; translate its error to StateError so the CLI prints
        # ERROR: and exits 1 instead of a traceback.
        try:
            require_complete_proof(data.get("report_validation"), data["session_id"])
        except ReportValidationError as exc:
            raise StateError(str(exc)) from exc
        proof = data["report_validation"]
        print(f"REPORT:{proof['path']}")
        print(f"REPORT_SHA256:{proof['sha256']}")
        print(f"MIN_SOURCES:{proof['min_sources']}")


def _verify_integrity_line(data: dict[str, Any], store: StateStore) -> None:
    """Print the INTEGRITY marker, recomputing the report hash for DONE.

    A DONE session must still match the fingerprint stored at completion:
    a changed report prints INTEGRITY:MISMATCH and a moved/deleted one
    INTEGRITY:MISSING, both raised as StateError so the CLI exits 1 with an
    ERROR: line instead of silently claiming OK. Non-DONE phases carry no
    proof to verify (STARTED never has one; add_dimensions clears it), so
    integrity stays vacuously OK there — the behaviour `check` predates on.

    The same contract covers the evidence ledger fingerprint half of the
    proof: appending a backdated row or deleting the ledger after DONE is
    reported with the same MISMATCH / MISSING markers.
    """
    if data["phase"] != "DONE":
        print("INTEGRITY:OK")
        return
    proof = data["report_validation"]  # emit() already asserted completeness
    try:
        verify_proof_integrity(proof)
    except ReportMissingError as exc:
        print("INTEGRITY:MISSING")
        raise StateError(str(exc)) from exc
    except ReportTamperedError as exc:
        print("INTEGRITY:MISMATCH")
        raise StateError(str(exc)) from exc
    # Ledger fingerprint half (lazy import: evidence.py imports this module).
    from evidence import (
        LedgerMissingError,
        LedgerTamperedError,
        evidence_path,
        verify_ledger_integrity,
    )

    try:
        verify_ledger_integrity(proof, evidence_path(store, data["session_id"]))
    except LedgerMissingError as exc:
        print("INTEGRITY:MISSING")
        raise StateError(str(exc)) from exc
    except LedgerTamperedError as exc:
        print("INTEGRITY:MISMATCH")
        raise StateError(str(exc)) from exc
    print("INTEGRITY:OK")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--session", help="Session id")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("start")
    subparsers.add_parser("check")
    subparsers.add_parser("get_phase")
    subparsers.add_parser("get_params")

    done_parser = subparsers.add_parser("done")
    done_parser.add_argument("--report", type=Path, required=True)
    done_parser.add_argument("--min-sources", type=source_threshold)

    params_parser = subparsers.add_parser("set_params")
    params_parser.add_argument("params_json")

    ext_parser = subparsers.add_parser("add_dimensions")
    ext_parser.add_argument("extension_json")
    return parser


def _parse_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StateError(f"invalid JSON: {exc.msg}") from exc


def run(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)

    if args.command == "start":
        data = store.start_session(args.session)
        print(f"OK:Session {data['session_id']} started")
        emit(data, store)
        return 0

    session_id = store.resolve_session(args.session)
    data = store.load(session_id)

    if args.command == "check":
        emit(data, store)
        _verify_integrity_line(data, store)
        return 0

    if args.command == "get_phase":
        # Emit SESSION marker before the phase value so external consumers
        # (CI scripts, dashboards) can attribute the phase to a specific
        # session id when the command is run against the active-session
        # fallback.
        print(f"SESSION:{session_id}")
        print(data["phase"])
        return 0

    if args.command == "get_params":
        if data.get("params") is None:
            raise StateError("parameters not set")
        # Same SESSION marker convention as get_phase, for parseable output.
        print(f"SESSION:{session_id}")
        print(json.dumps(data["params"], ensure_ascii=False))
        return 0

    if args.command == "set_params":
        data = store.set_params(session_id, _parse_json(args.params_json))
        print("OK:Parameters saved")
        return 0

    if args.command == "add_dimensions":
        data = store.extend(session_id, _parse_json(args.extension_json))
        print(f"OK:Session {session_id} extended")
        emit(data, store)
        return 0

    if args.command == "done":
        data = store.complete(session_id, args.report, args.min_sources)
        print(f"OK:Session {session_id} completed")
        emit(data, store)
        return 0

    raise StateError(f"unsupported command: {args.command}")


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except StateError as exc:
        # Flush stdout first so merged-stream consumers (the Lead Agent's
        # Bash, CI `2>&1`) see the STATE:/.../INTEGRITY: markers before the
        # ERROR: line, which a line-by-line parser must be able to attribute
        # to the INTEGRITY check rather than to command start-up.
        sys.stdout.flush()
        print(f"ERROR:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

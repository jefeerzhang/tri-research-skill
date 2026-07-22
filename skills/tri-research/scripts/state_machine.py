#!/usr/bin/env python3
"""简化版状态机：start（初始化）→ done（验证完成）。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make sibling `validate_report` and `_common` importable regardless of how
# this file is invoked. Direct script execution (python state_machine.py)
# already prepends the script's directory to sys.path[0], but importlib-based
# loaders (e.g. `importlib.util.spec_from_file_location` used by tests and
# external tooling) do NOT. Without this injection, `from validate_report
# import validate` fails with ModuleNotFoundError on those code paths.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _common import MIN_REPORT_SOURCES, source_threshold  # noqa: E402
from validate_report import validate as validate_report  # noqa: E402

SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class StateError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_state_dir() -> Path:
    configured = os.environ.get("TRI_RESEARCH_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(tempfile.gettempdir()) / "tri-research-state"


def validate_session_id(session_id: str) -> str:
    if not SESSION_RE.fullmatch(session_id):
        raise StateError("session id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    return session_id


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


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


class StateStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.active_file = self.state_dir / "active-session"

    def state_path(self, session_id: str) -> Path:
        return self.state_dir / f"{validate_session_id(session_id)}.json"

    def set_active(self, session_id: str) -> None:
        self._atomic_write_text(self.active_file, session_id + "\n")

    def clear_active(self) -> None:
        """Remove the active-session pointer.

        Called after a session transitions to DONE so that subsequent
        callers who run a read command without --session get the
        'no active session' error instead of silently receiving a
        completed session's state.
        """
        try:
            self.active_file.unlink()
        except FileNotFoundError:
            pass  # already gone — no-op

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

    def save(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        self._atomic_write_text(self.state_path(data["session_id"]), payload)

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)


def emit(data: dict[str, Any], store: StateStore) -> None:
    phase = data["phase"]
    print(f"STATE:{phase}")
    print(f"SESSION:{data['session_id']}")
    print(f"FILE:{store.state_path(data['session_id'])}")
    if phase == "DONE":
        # A DONE phase MUST carry report_validation — without it, the state
        # file is corrupt (either someone edited it by hand, or a future
        # code path advanced phase=DONE without populating the proof).
        # Refuse to print a sanitized view; raise loudly so the corruption
        # is visible instead of silently swallowed.
        if "report_validation" not in data or not data["report_validation"]:
            raise StateError(
                f"phase=DONE but report_validation is missing for session "
                f"{data['session_id']!r} — state file is corrupt"
            )
        proof = data["report_validation"]
        print(f"REPORT:{proof['path']}")
        print(f"REPORT_SHA256:{proof['sha256']}")
        print(f"MIN_SOURCES:{proof['min_sources']}")


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
    return parser


def run(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)

    if args.command == "start":
        session_id = validate_session_id(
            args.session or datetime.now().strftime("research-%Y%m%d-%H%M%S")
        )
        path = store.state_path(session_id)
        if path.exists():
            raise StateError(f"session already exists: {session_id}")
        timestamp = now_iso()
        data = {
            "session_id": session_id,
            "schema_version": 3,
            "phase": "STARTED",
            "params": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "history": [{"phase": "STARTED", "at": timestamp}],
        }
        store.save(data)
        store.set_active(session_id)
        print(f"OK:Session {session_id} started")
        emit(data, store)
        return 0

    session_id = store.resolve_session(args.session)
    data = store.load(session_id)

    if args.command == "check":
        emit(data, store)
        print("INTEGRITY:OK")
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
        if data["phase"] != "STARTED":
            raise StateError("parameters can only be set in STARTED phase")
        if data.get("params") is not None:
            raise StateError("parameters already set and immutable")
        try:
            params = json.loads(args.params_json)
        except json.JSONDecodeError as exc:
            raise StateError(f"invalid JSON: {exc.msg}") from exc
        params = validate_params(params)
        data["params"] = params
        data["updated_at"] = now_iso()
        store.save(data)
        print("OK:Parameters saved")
        return 0

    if args.command == "done":
        if data["phase"] == "DONE":
            raise StateError("session already completed")
        params = data.get("params")
        if params is None:
            raise StateError("parameters not set; run set_params first")
        report_path = args.report.expanduser().resolve()
        if not report_path.is_file():
            raise StateError(f"report does not exist: {report_path}")
        try:
            report_text = report_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateError(f"cannot read report: {exc}") from exc
        min_sources = params["min_sources"]
        if args.min_sources is not None and args.min_sources != min_sources:
            raise StateError(
                f"--min-sources does not match confirmed min_sources ({min_sources})"
            )
        errors = validate_report(report_text, min_sources, expected_topic=params["topic"])
        if errors:
            raise StateError("validation failed: " + "; ".join(errors))
        report_bytes = report_path.read_bytes()
        timestamp = now_iso()
        data["phase"] = "DONE"
        data["updated_at"] = timestamp
        data["report_validation"] = {
            "path": str(report_path),
            "sha256": sha256_bytes(report_bytes),
            "topic": params["topic"],
            "min_sources": min_sources,
            "validated_at": timestamp,
        }
        data["history"].append({"phase": "DONE", "at": timestamp})
        store.save(data)
        # Clear the active-session pointer: this session is now completed
        # and the pointer must not silently redirect subsequent no-arg
        # read commands to it.
        store.clear_active()
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
        print(f"ERROR:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


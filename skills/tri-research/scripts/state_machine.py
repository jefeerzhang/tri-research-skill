#!/usr/bin/env python3
"""Session-isolated state machine for tri-research."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASES = ("S0", "S1", "S2", "S3", "DONE")
TRANSITIONS = {"S0": "S1", "S1": "S2", "S2": "S3", "S3": "DONE"}
EVENTS = {
    "S0": "INIT",
    "S1": "SCOPE_CONFIRMED",
    "S2": "SUBAGENTS_DISPATCHED",
    "S3": "SUBAGENTS_RETURNED",
    "DONE": "REPORT_VALIDATED",
}
MESSAGES = {
    "S0": "Phase 0 CLARIFY: waiting for scope confirmation. Do not dispatch subagents.",
    "S1": "Scope confirmed. Complete assessment and planning before advancing to S2.",
    "S2": "Subagents dispatched. Wait for all results; do not dispatch again.",
    "S3": "Synthesis stage. Write and validate the cited report.",
    "DONE": "Research completed and report validated. Do not restart this session.",
}
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
        raise StateError(
            "session id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}"
        )
    return session_id


class StateStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.active_file = self.state_dir / "active-session"

    def state_path(self, session_id: str) -> Path:
        return self.state_dir / f"{validate_session_id(session_id)}.json"

    def set_active(self, session_id: str) -> None:
        self._atomic_write_text(self.active_file, session_id + "\n")

    def resolve_session(self, requested: str | None) -> str:
        if requested:
            return validate_session_id(requested)
        if not self.active_file.exists():
            raise StateError("no active research session; run init first or pass --session")
        return validate_session_id(self.active_file.read_text(encoding="utf-8").strip())

    def load(self, session_id: str) -> dict[str, Any]:
        path = self.state_path(session_id)
        if not path.exists():
            raise StateError(f"research session does not exist: {session_id}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"invalid state file for session {session_id}: {exc}") from exc
        if data.get("phase") not in PHASES:
            raise StateError(f"invalid phase in session {session_id}")
        return data

    def save(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        self._atomic_write_text(self.state_path(data["session_id"]), payload)

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)


def emit_state(data: dict[str, Any], store: StateStore) -> None:
    phase = data["phase"]
    print(f"STATE:{phase}")
    print(f"SESSION:{data['session_id']}")
    print(f"FILE:{store.state_path(data['session_id'])}")
    print(f"MESSAGE:{MESSAGES[phase]}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--session", help="Explicit research session id")
    parser.add_argument("--force", action="store_true", help="Replace an existing session on init")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("research_id", nargs="?")
    subparsers.add_parser("check")

    advance_parser = subparsers.add_parser("advance")
    advance_parser.add_argument("phase", choices=PHASES[1:])

    subparsers.add_parser("get_phase")

    done_parser = subparsers.add_parser("is_phase_done")
    done_parser.add_argument("phase", choices=PHASES[:-1])

    subparsers.add_parser("get_params")

    params_parser = subparsers.add_parser("set_params")
    params_parser.add_argument("params_json")
    return parser


def run(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)

    if args.command == "init":
        session_id = validate_session_id(
            args.session or args.research_id or datetime.now().strftime("research-%Y%m%d-%H%M%S")
        )
        path = store.state_path(session_id)
        if path.exists() and not args.force:
            raise StateError(f"research session already exists: {session_id}; use --force to replace it")
        timestamp = now_iso()
        data = {
            "session_id": session_id,
            "phase": "S0",
            "params": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "history": [{"phase": "S0", "event": EVENTS["S0"], "at": timestamp}],
        }
        store.save(data)
        store.set_active(session_id)
        print(f"OK:Initialized research session {session_id}")
        emit_state(data, store)
        return 0

    session_id = store.resolve_session(args.session)
    data = store.load(session_id)

    if args.command == "check":
        emit_state(data, store)
        return 0

    if args.command == "advance":
        current = data["phase"]
        expected = TRANSITIONS.get(current)
        if expected != args.phase:
            if current == "DONE":
                raise StateError("research session is already DONE")
            raise StateError(f"cannot advance from {current} to {args.phase}; expected {expected}")
        timestamp = now_iso()
        data["phase"] = args.phase
        data["updated_at"] = timestamp
        data["history"].append(
            {"phase": args.phase, "event": EVENTS[args.phase], "at": timestamp}
        )
        store.save(data)
        print(f"OK:Advanced research session {session_id} to {args.phase}")
        emit_state(data, store)
        return 0

    if args.command == "get_phase":
        print(data["phase"])
        return 0

    if args.command == "is_phase_done":
        print("YES" if PHASES.index(data["phase"]) > PHASES.index(args.phase) else "NO")
        return 0

    if args.command == "set_params":
        try:
            params = json.loads(args.params_json)
        except json.JSONDecodeError as exc:
            raise StateError(f"params must be valid JSON: {exc.msg}") from exc
        if not isinstance(params, dict):
            raise StateError("params must be a JSON object")
        data["params"] = params
        data["updated_at"] = now_iso()
        store.save(data)
        print("OK:Parameters saved")
        return 0

    if args.command == "get_params":
        if data.get("params") is None:
            raise StateError("parameters have not been set")
        print(json.dumps(data["params"], ensure_ascii=False))
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

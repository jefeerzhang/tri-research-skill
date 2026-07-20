#!/usr/bin/env python3
"""Session-isolated state machine for tri-research."""

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

from validate_report import validate as validate_report

PHASES = ("S0", "S1", "S2", "S3", "DONE")
TRANSITIONS = {"S0": "S1", "S1": "S2", "S2": "S3", "S3": "DONE"}
EVENTS = {
    "S0": "INIT",
    "S1": "SCOPE_CONFIRMED",
    "S2": "SUBAGENTS_DISPATCHED",
    "S3": "SUBAGENTS_RETURNED",
    "DONE": "REPORT_VALIDATED",
}
MIN_REPORT_SOURCES = 10
MAX_SUBAGENTS = 10
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
        raise StateError("session id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    return session_id


def source_threshold(value: str) -> int:
    parsed = int(value)
    if parsed < MIN_REPORT_SOURCES:
        raise argparse.ArgumentTypeError(f"must be at least {MIN_REPORT_SOURCES}")
    return parsed


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_json_hash(value: Any) -> str:
    content = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(content)


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


def verify_artifact(path_value: str, expected_hash: str, label: str) -> None:
    path = Path(path_value)
    if not path.is_file():
        raise StateError(f"{label} is missing: {path}")
    try:
        actual_hash = sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise StateError(f"cannot read {label}: {exc}") from exc
    if actual_hash != expected_hash:
        raise StateError(f"{label} hash mismatch: {path}")


def verify_agent_artifacts(data: dict[str, Any]) -> None:
    for agent_id, agent in data.get("agents", {}).items():
        if agent.get("status") == "returned":
            verify_artifact(
                agent["result_path"], agent["result_sha256"], f"agent {agent_id} result"
            )


def verify_done_integrity(data: dict[str, Any]) -> None:
    proof = data.get("report_validation")
    if not isinstance(proof, dict):
        raise StateError("DONE session has no report validation proof")
    verify_artifact(proof["path"], proof["sha256"], "report")


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
            raise StateError(
                "no active research session; run init first or pass --session"
            )
        return validate_session_id(self.active_file.read_text(encoding="utf-8").strip())

    def load(self, session_id: str) -> dict[str, Any]:
        path = self.state_path(session_id)
        if not path.exists():
            raise StateError(f"research session does not exist: {session_id}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(
                f"invalid state file for session {session_id}: {exc}"
            ) from exc
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
    agents = data.get("agents", {})
    if agents:
        statuses = ",".join(
            f"{agent_id}={agent['status']}"
            for agent_id, agent in sorted(agents.items())
        )
        print(f"AGENTS:{statuses}")
    proof = data.get("report_validation")
    if phase == "DONE" and proof:
        print(f"REPORT:{proof['path']}")
        print(f"REPORT_SHA256:{proof['sha256']}")
        print(f"MIN_SOURCES:{proof['min_sources']}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--session", help="Explicit research session id")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("research_id", nargs="?")
    subparsers.add_parser("check")

    advance_parser = subparsers.add_parser("advance")
    advance_parser.add_argument("phase", choices=PHASES[1:])
    advance_parser.add_argument("--report", type=Path)
    advance_parser.add_argument("--min-sources", type=source_threshold)

    subparsers.add_parser("get_phase")

    done_parser = subparsers.add_parser("is_phase_done")
    done_parser.add_argument("phase", choices=PHASES[:-1])

    subparsers.add_parser("get_params")

    params_parser = subparsers.add_parser("set_params")
    params_parser.add_argument("params_json")

    dispatch_parser = subparsers.add_parser("record_dispatch")
    dispatch_parser.add_argument("agent_id")
    dispatch_parser.add_argument("--objective", required=True)
    dispatch_parser.add_argument("--dispatch-ref", required=True)

    result_parser = subparsers.add_parser("record_result")
    result_parser.add_argument("agent_id")
    result_parser.add_argument(
        "--status", choices=("returned", "failed", "timed_out"), default="returned"
    )
    result_parser.add_argument("--result", type=Path)
    result_parser.add_argument("--detail")
    return parser


def run(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)

    if args.command == "init":
        session_id = validate_session_id(
            args.session
            or args.research_id
            or datetime.now().strftime("research-%Y%m%d-%H%M%S")
        )
        path = store.state_path(session_id)
        if path.exists():
            raise StateError(
                f"research session already exists: {session_id}; use a new session id"
            )
        timestamp = now_iso()
        data = {
            "session_id": session_id,
            "schema_version": 2,
            "phase": "S0",
            "params": None,
            "scope": None,
            "agents": {},
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

    if data["phase"] == "DONE" and args.command in {
        "check",
        "get_phase",
        "is_phase_done",
    }:
        verify_agent_artifacts(data)
        verify_done_integrity(data)

    if args.command == "check":
        if data["phase"] != "DONE":
            verify_agent_artifacts(data)
        emit_state(data, store)
        print("INTEGRITY:OK")
        return 0

    if args.command == "advance":
        current = data["phase"]
        expected = TRANSITIONS.get(current)
        if expected != args.phase:
            if current == "DONE":
                raise StateError("research session is already DONE")
            raise StateError(
                f"cannot advance from {current} to {args.phase}; expected {expected}"
            )
        if args.phase == "S1":
            params = data.get("params")
            if params is None:
                raise StateError(
                    "scope is not confirmed; run set_params before advancing to S1"
                )
            timestamp = now_iso()
            data["scope"] = {
                "topic": params["topic"],
                "min_sources": params["min_sources"],
                "params_sha256": canonical_json_hash(params),
                "bound_at": timestamp,
            }
        elif args.phase == "S2":
            agents = data.get("agents", {})
            if not agents or any(
                agent.get("status") != "dispatched" for agent in agents.values()
            ):
                raise StateError(
                    "S2 requires dispatch evidence for every planned subagent"
                )
        elif args.phase == "S3":
            agents = data.get("agents", {})
            nonterminal = sorted(
                agent_id
                for agent_id, agent in agents.items()
                if agent.get("status") not in {"returned", "failed", "timed_out"}
            )
            if nonterminal:
                raise StateError(
                    "subagents are not terminal: " + ", ".join(nonterminal)
                )
            if not any(agent.get("status") == "returned" for agent in agents.values()):
                raise StateError("S3 requires at least one returned subagent result")
            verify_agent_artifacts(data)
        validation_proof = None
        if args.phase == "DONE":
            if args.report is None:
                raise StateError(
                    "advancing to DONE requires --report; the report must pass validation"
                )
            report_path = args.report.expanduser().resolve()
            if not report_path.is_file():
                raise StateError(f"report does not exist: {report_path}")
            try:
                report_bytes = report_path.read_bytes()
                report_text = report_bytes.decode("utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise StateError(f"cannot read report as UTF-8: {exc}") from exc
            scope = data.get("scope")
            if not isinstance(scope, dict):
                raise StateError("confirmed scope is missing")
            min_sources = scope["min_sources"]
            if args.min_sources is not None and args.min_sources != min_sources:
                raise StateError(
                    "--min-sources does not match confirmed min_sources "
                    f"({min_sources})"
                )
            validation_errors = validate_report(
                report_text, min_sources, expected_topic=scope["topic"]
            )
            if validation_errors:
                raise StateError(
                    "report validation failed: " + "; ".join(validation_errors)
                )
            validation_proof = {
                "path": str(report_path),
                "sha256": sha256_bytes(report_bytes),
                "topic": scope["topic"],
                "min_sources": min_sources,
            }
        elif args.report is not None or args.min_sources is not None:
            raise StateError(
                "--report and --min-sources are only valid when advancing to DONE"
            )

        timestamp = now_iso()
        data["phase"] = args.phase
        data["updated_at"] = timestamp
        history_entry = {
            "phase": args.phase,
            "event": EVENTS[args.phase],
            "at": timestamp,
        }
        if validation_proof is not None:
            validation_proof["validated_at"] = timestamp
            data["report_validation"] = validation_proof
            history_entry["report_sha256"] = validation_proof["sha256"]
            history_entry["min_sources"] = validation_proof["min_sources"]
        data["history"].append(history_entry)
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
        if data["phase"] != "S0":
            raise StateError("parameters can only be set in S0")
        if data.get("params") is not None:
            raise StateError("parameters have already been set and are immutable")
        try:
            params = json.loads(args.params_json)
        except json.JSONDecodeError as exc:
            raise StateError(f"params must be valid JSON: {exc.msg}") from exc
        params = validate_params(params)
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

    if args.command == "record_dispatch":
        if data["phase"] != "S1":
            raise StateError("dispatch evidence can only be recorded in S1")
        agent_id = validate_session_id(args.agent_id)
        objective = require_text(args.objective, "objective")
        dispatch_ref = require_text(args.dispatch_ref, "dispatch_ref")
        agents = data.setdefault("agents", {})
        if agent_id in agents:
            raise StateError(f"subagent already recorded: {agent_id}")
        if len(agents) >= MAX_SUBAGENTS:
            raise StateError(f"cannot record more than {MAX_SUBAGENTS} subagents")
        if any(agent.get("dispatch_ref") == dispatch_ref for agent in agents.values()):
            raise StateError(f"dispatch_ref must be unique: {dispatch_ref}")
        timestamp = now_iso()
        agents[agent_id] = {
            "objective": objective,
            "objective_sha256": sha256_bytes(objective.encode("utf-8")),
            "dispatch_ref": dispatch_ref,
            "dispatched_at": timestamp,
            "status": "dispatched",
        }
        data["updated_at"] = timestamp
        store.save(data)
        print(f"OK:Recorded dispatch for {agent_id}")
        return 0

    if args.command == "record_result":
        if data["phase"] != "S2":
            raise StateError("subagent results can only be recorded in S2")
        agent_id = validate_session_id(args.agent_id)
        agents = data.get("agents", {})
        if agent_id not in agents:
            raise StateError(f"unknown subagent: {agent_id}")
        agent = agents[agent_id]
        if agent.get("status") != "dispatched":
            raise StateError(f"subagent already has a terminal result: {agent_id}")
        timestamp = now_iso()
        if args.status == "returned":
            if args.result is None or args.detail is not None:
                raise StateError(
                    "returned status requires --result and does not accept --detail"
                )
            result_path = args.result.expanduser().resolve()
            if not result_path.is_file():
                raise StateError(f"subagent result does not exist: {result_path}")
            try:
                result_bytes = result_path.read_bytes()
            except OSError as exc:
                raise StateError(f"cannot read subagent result: {exc}") from exc
            if not result_bytes:
                raise StateError(f"subagent result is empty: {result_path}")
            agent.update(
                {
                    "status": "returned",
                    "returned_at": timestamp,
                    "result_path": str(result_path),
                    "result_sha256": sha256_bytes(result_bytes),
                }
            )
        else:
            if args.result is not None or not args.detail:
                raise StateError(
                    f"{args.status} status requires --detail and does not accept --result"
                )
            agent.update(
                {
                    "status": args.status,
                    "returned_at": timestamp,
                    "detail": require_text(args.detail, "detail"),
                }
            )
        data["updated_at"] = timestamp
        store.save(data)
        print(f"OK:Recorded {args.status} result for {agent_id}")
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

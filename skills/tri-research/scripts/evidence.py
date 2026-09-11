#!/usr/bin/env python3
"""Evidence Ledger CLI：会话级 append-only 证据流水账（登记 / 翻阅）。

台账（Evidence Ledger，见 CONTEXT.md）与 state JSON 并排放在状态目录，
每会话一个 ``{session_id}.evidence.jsonl``，只追加不修改。每条记录
（Evidence Record）只可能是两种 kind 之一：

- ``seen``：一次搜索结果里的一个 URL（backend / query / url / title / ts）
- ``user_provided``：用户手动提供的资料（url / note / ts）

写入不做去重——同一 URL 被两条 query 搜到就记两行，台账是流水账不是字典。
溯源对账（Evidence Audit，``audit`` 命令）把报告参考文献与台账比对，
也是 ``state_machine.py done`` 的硬门禁：报告里每条引用 URL 经统一归一化
后必须能在台账命中，untraced 即失败。

报告的解析归 _report_parse.py（与验收器、外壳同一份语法），密钥与状态机的契约
归 state_machine.py / validate_report.py；本模块只管台账的写入与比对，
不调用任何搜索后端。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# Make sibling modules importable regardless of how this file is invoked.
# Direct script execution (python evidence.py) already prepends the script's
# directory to sys.path[0], but importlib-based loaders (tests, external
# tooling) do NOT — same bootstrap as state_machine.py / validate_report.py.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _common import StateError, now_iso  # noqa: E402
from _report_parse import canonicalize_url, parse_report  # noqa: E402
from state_machine import (  # noqa: E402
    StateStore,
    default_state_dir,
    validate_session_id,
)
from validate_report import (  # noqa: E402
    ReportValidationError,
    sha256_bytes,
)

KIND_SEEN = "seen"
KIND_USER_PROVIDED = "user_provided"
RECORD_KINDS = (KIND_SEEN, KIND_USER_PROVIDED)


class LedgerIntegrityError(ReportValidationError):
    """Ledger half of the DONE proof verification failed."""


class LedgerMissingError(LedgerIntegrityError):
    """The evidence ledger can no longer be read (deleted or moved)."""


class LedgerTamperedError(LedgerIntegrityError):
    """The ledger bytes changed after the DONE proof recorded its fingerprint."""


class EvidenceAuditFailed(StateError):
    """Evidence Audit found report references with no ledger hit.

    Owns the one sentence both callers must agree on — the ``untraced/total``
    count — and carries the pairs themselves, so each caller appends only its
    own layer (the `done` gate adds the detail list, the `audit` command adds
    the registration guidance). Subclasses StateError because `done` raises it
    from inside the state machine, whose CLI catches that class.
    """

    def __init__(self, untraced: list[tuple[int, str]], total: int) -> None:
        super().__init__(f"evidence audit failed: {len(untraced)}/{total} reference URL(s) untraced")
        self.untraced = untraced
        self.total = total

    def detail(self) -> str:
        """Full detail list for the DONE gate — no truncation by design."""
        return "; ".join(f"[{number}] {url}" for number, url in self.untraced)


def evidence_path(store: StateStore, session_id: str) -> Path:
    """Ledger file for a session, next to its state JSON in the state dir."""
    return store.state_dir / f"{validate_session_id(session_id)}.evidence.jsonl"


def validate_url(value: str) -> str:
    """Accept absolute http(s) URLs only — same floor as report references."""
    url = value.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise StateError(f"url must be an absolute http(s) URL: {value!r}")
    return url


def build_records(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Build the records for one `add` invocation, validating kind rules."""
    timestamp = now_iso()
    urls = [validate_url(url) for url in args.url]
    if args.user_provided:
        if args.backend or args.query or args.title:
            raise StateError("--user-provided records take --url/--note only (no --backend/--query/--title)")
        return [
            {"kind": KIND_USER_PROVIDED, "ts": timestamp, "url": url, **({"note": args.note} if args.note else {})}
            for url in urls
        ]
    if not args.backend or not args.backend.strip():
        raise StateError("--backend is required for seen records (or pass --user-provided)")
    if not args.query or not args.query.strip():
        raise StateError("--query is required for seen records (or pass --user-provided)")
    return [
        {
            "kind": KIND_SEEN,
            "ts": timestamp,
            "backend": args.backend.strip(),
            "query": args.query.strip(),
            "url": url,
            **({"title": args.title} if args.title else {}),
        }
        for url in urls
    ]


def require_open_session(store: StateStore, session_id: str) -> dict[str, Any]:
    """Load a session and refuse ledger writes once it is DONE.

    After DONE the ledger is sealed under the proof's fingerprint: appending
    rows would silently break INTEGRITY at `check`. Extending research goes
    through add_dimensions first, which reopens the session (EXTENDED) and
    the next `done` refreshes the fingerprint.
    """
    data = store.load(session_id)
    if data["phase"] == "DONE":
        raise StateError("session completed: evidence ledger is sealed (run add_dimensions to extend first)")
    return data


def append_records(store: StateStore, session_id: str, records: list[dict[str, Any]]) -> Path:
    """Append records to the ledger under the session's write lock.

    One lock guards both the state JSON and the ledger file, so appends
    serialize against set_params / add_dimensions / done exactly like the
    existing mutating commands do. A whole batch lands as one write.
    """
    path = evidence_path(store, session_id)
    payload = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    with store.write_lock(session_id):
        require_open_session(store, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n" keeps the ledger byte-stable across platforms: the
        # DONE proof will fingerprint the raw file, and CRLF differences
        # between OSes would otherwise make the same ledger hash differently.
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    return path


def seen_records_from_hits(
    backend: str,
    hits_by_query: Mapping[str, Sequence[Any]],
) -> list[dict[str, Any]]:
    """Build ``seen`` rows from search hits without inventing a second ledger format.

    Each hit may spell the URL as ``url`` (Exa / Tavily) or ``link`` (SerpApi
    organic). Invalid / non-http(s) URLs are skipped so a junk SERP row cannot
    fail a successful search; an empty return means there was nothing to write.
    """
    timestamp = now_iso()
    name = backend.strip()
    records: list[dict[str, Any]] = []
    for query, items in hits_by_query.items():
        q = str(query).strip()
        if not name or not q:
            continue
        for item in items or []:
            if not isinstance(item, dict):
                continue
            raw = item.get("url") or item.get("link") or ""
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                url = validate_url(raw)
            except StateError:
                continue
            record: dict[str, Any] = {
                "kind": KIND_SEEN,
                "ts": timestamp,
                "backend": name,
                "query": q,
                "url": url,
            }
            title = item.get("title")
            if isinstance(title, str) and title.strip():
                record["title"] = title.strip()
            records.append(record)
    return records


def append_seen_hits(
    store: StateStore,
    session_id: str,
    *,
    backend: str,
    hits_by_query: Mapping[str, Sequence[Any]],
) -> Path | None:
    """Append ``seen`` hits for one search/batch success. No-op when nothing to write."""
    records = seen_records_from_hits(backend, hits_by_query)
    if not records:
        return None
    return append_records(store, session_id, records)


def load_records(path: Path) -> list[dict[str, Any]]:
    """Read ledger records, tolerating a truncated final line.

    A crash mid-append can leave a half-written last line; it is dropped
    with a warning and everything before it stands. Corruption anywhere
    else (a broken line with data after it) is NOT tolerated — silently
    skipping middle rows would quietly weaken later audits.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) - 1:
                print(f"WARNING:dropped truncated last line in {path}", file=sys.stderr)
                break
            raise StateError(f"corrupt ledger line {index + 1} in {path}: {exc}") from exc
        if not isinstance(record, dict) or record.get("kind") not in RECORD_KINDS:
            raise StateError(f"invalid evidence record at line {index + 1} in {path}")
        records.append(record)
    return records


def report_reference_urls(report_path: Path) -> dict[int, str]:
    """Extract canonical reference URLs (number → canonical URL) from a report.

    The whole grammar comes from :func:`_report_parse.parse_report` — the same
    seam the structural gate reads — so the audit and the gate cannot drift
    apart about which URL a reference carries. Entries whose URL fails
    canonicalization are omitted here; the validator already rejects those
    reports before ``done`` reaches this point.
    """
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StateError(f"cannot read report: {exc}") from exc
    return {
        reference.number: reference.canonical_url
        for reference in parse_report(text).references
        if reference.canonical_url is not None
    }


def ledger_urls(records: list[dict[str, Any]]) -> set[str]:
    """Canonical URL set of a ledger; `user_provided` hits exactly like `seen`."""
    known: set[str] = set()
    for record in records:
        canonical_url = canonicalize_url(str(record.get("url", "")))
        if canonical_url is not None:
            known.add(canonical_url)
    return known


def audit_report(
    store: StateStore,
    session_id: str,
    report_path: Path,
) -> int:
    """Evidence Audit: report references against the session ledger.

    Returns the number of canonical reference URLs checked; raises
    :class:`EvidenceAuditFailed` when any of them has no ledger hit. An
    empty/missing ledger is not special-cased: it makes every reference
    untraced. Raises StateError for a corrupt ledger or unreadable report.
    """
    known = ledger_urls(load_records(evidence_path(store, session_id)))
    reference_urls = report_reference_urls(report_path)
    untraced = [(number, url) for number, url in sorted(reference_urls.items()) if url not in known]
    if untraced:
        raise EvidenceAuditFailed(untraced, len(reference_urls))
    return len(reference_urls)


def _print_summary(records: list[dict[str, Any]]) -> None:
    """Per-backend counts for the 执行情况「搜索源使用」row.

    ``queries`` counts DISTINCT (backend, query) pairs — the closest
    machine-verifiable proxy for "how many searches this backend ran";
    ``urls`` counts registered records (repeats across queries included).
    Backends absent from the ledger are the caller's job to report as 0.
    """
    queries: dict[str, set[str]] = {}
    url_counts: dict[str, int] = {}
    for record in records:
        backend = str(record.get("backend") or record["kind"])
        queries.setdefault(backend, set()).add(str(record.get("query", "")))
        url_counts[backend] = url_counts.get(backend, 0) + 1
    for backend in sorted(queries):
        print(f"SUMMARY:{backend} queries={len(queries[backend])} urls={url_counts[backend]}")


def ledger_fingerprint(store: StateStore, session_id: str) -> dict[str, Any]:
    """Snapshot fingerprint of the ledger, stored in the DONE proof.

    ``evidence_lines`` is the parsed record count (human-readable); the
    SHA-256 covers the raw file bytes with the same recipe as the report
    proof — so any post-DONE byte change, including appending a backdated
    row, shifts the fingerprint and trips INTEGRITY at `check`.
    """
    path = evidence_path(store, session_id)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raw = b""  # empty ledger (audit would have failed first; defensive)
    return {
        "evidence_lines": len(load_records(path)),
        "evidence_sha256": sha256_bytes(raw),
    }


def verify_ledger_integrity(proof: dict[str, Any], ledger_path: Path) -> None:
    """Recompute the ledger's SHA-256 and compare with the DONE fingerprint.

    Verification half of the ledger lifecycle, mirroring
    ``validate_report.verify_proof_integrity``: reads raw bytes with the
    same recipe as fingerprint-building. Raises LedgerMissingError when
    the file cannot be read and LedgerTamperedError when its bytes no
    longer match — both subclass ReportValidationError so callers already
    handling that base type keep working.
    """
    expected_sha = proof.get("evidence_sha256")
    if not expected_sha:
        raise LedgerMissingError(f"proof has no evidence ledger fingerprint: {ledger_path}")
    try:
        raw = ledger_path.read_bytes()
    except OSError as exc:
        raise LedgerMissingError(f"evidence ledger not readable: {ledger_path} ({exc})") from exc
    if sha256_bytes(raw) != expected_sha:
        raise LedgerTamperedError(f"evidence ledger changed after DONE: {ledger_path}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--session", help="Session id (defaults to the active session)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Append records to the ledger")
    add_parser.add_argument("--url", action="append", required=True, help="URL seen or provided (repeatable)")
    add_parser.add_argument("--backend", help="Search backend that produced the URLs (seen records)")
    add_parser.add_argument("--query", help="Query that produced the URLs (seen records)")
    add_parser.add_argument("--title", help="Optional shared result title (seen records)")
    add_parser.add_argument("--user-provided", action="store_true", help="Record user-provided material instead")
    add_parser.add_argument("--note", help="Optional note for user-provided records")

    list_parser = subparsers.add_parser("list", help="Print ledger records (JSON lines)")
    list_parser.add_argument("--kind", choices=RECORD_KINDS, help="Filter by record kind")
    list_parser.add_argument(
        "--summary", action="store_true", help="Per-backend query/URL counts (for the 搜索源使用 row)"
    )

    audit_parser = subparsers.add_parser("audit", help="Trace report references against the ledger")
    audit_parser.add_argument("--report", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir if args.state_dir is not None else default_state_dir())
    session_id = store.resolve_session(args.session)

    if args.command == "add":
        # Fail fast on an unknown session BEFORE flag validation, so callers
        # get "session does not exist" instead of a flag complaint first.
        store.load(session_id)
        records = build_records(args)
        path = append_records(store, session_id, records)
        print(f"OK:Recorded {len(records)} evidence record(s)")
        print(f"SESSION:{session_id}")
        print(f"FILE:{path}")
        return 0

    if args.command == "list":
        store.load(session_id)  # unknown session is an error, not an empty ledger
        print(f"SESSION:{session_id}")
        records = load_records(evidence_path(store, session_id))
        if args.summary:
            _print_summary(records)
            return 0
        for record in records:
            if args.kind is None or record["kind"] == args.kind:
                print(json.dumps(record, ensure_ascii=False))
        return 0

    if args.command == "audit":
        store.load(session_id)  # unknown session is an error, not an empty ledger
        report_path = args.report.expanduser()
        if not report_path.is_file():
            raise StateError(f"report does not exist: {report_path}")
        try:
            total = audit_report(store, session_id, report_path)
        except EvidenceAuditFailed as exc:
            # Full detail, one line per miss: the caller (Lead Agent) needs
            # exactly these to know which references to register. The count
            # sentence itself is the exception's — `done` says the same thing.
            for number, url in exc.untraced:
                print(f"UNTRACED:[{number}] {url}")
            raise StateError(f"{exc}; register them via 'evidence.py add' before done") from exc
        print(f"OK:all {total} reference URL(s) traced to the evidence ledger")
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

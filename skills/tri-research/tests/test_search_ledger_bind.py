"""ADR-0010: successful Machine-backend search optionally binds to the Evidence Ledger.

Seam: ``_search_cli.search`` / ``batch_search`` / ``bind_successful_search_to_ledger``
with FakeBackend standing in for the SDK. Ledger writes go through
``evidence.append_seen_hits`` → ``append_records`` (no second format).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from _test_helpers import required_backend_cli_env

SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _search_cli  # noqa: E402
import evidence as evidence_mod  # noqa: E402

STATE_MACHINE = SCRIPT_DIR / "state_machine.py"
SERPAPI = Path(__file__).parents[2] / "serpapi" / "scripts" / "serpapi_cli.py"


class FakeBackend(_search_cli.Backend):
    name = "Fake"
    help = "Fake backend for ledger-bind tests"
    sdk = object()
    missing_sdk_message = "fake-sdk not installed"
    env_key = "FAKE_SEARCH_KEY"
    client_factory = staticmethod(lambda key: object())
    flags = ()
    max_attempts = 1
    retry_backoff = 0.0
    call_timeout = 5.0

    def __init__(self, results: list[dict] | None = None) -> None:
        self.results = results if results is not None else [{"title": "ok", "url": "https://publisher.org/item"}]

    def probe(self, client: object) -> bool:
        return True

    def search(self, client: object, query: str, options: dict) -> dict:
        return {"results": list(self.results)}


class SearchLedgerBindTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name) / "state"
        self._old_key = os.environ.get("FAKE_SEARCH_KEY")
        os.environ["FAKE_SEARCH_KEY"] = "test-key"

    def tearDown(self) -> None:
        if self._old_key is None:
            os.environ.pop("FAKE_SEARCH_KEY", None)
        else:
            os.environ["FAKE_SEARCH_KEY"] = self._old_key
        self.tmp.cleanup()

    def start_session(self, session: str) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(STATE_MACHINE),
                "--state-dir",
                str(self.state_dir),
                "--session",
                session,
                "start",
            ],
            capture_output=True,
            text=True,
            env=required_backend_cli_env(),
        )
        if result.returncode != 0:
            self.fail(f"start failed: stdout={result.stdout}\nstderr={result.stderr}")

    def run_cli(self, backend: FakeBackend, argv: list[str]) -> tuple[str, int]:
        buf = io.StringIO()
        code = 0
        with redirect_stdout(buf):
            try:
                code = int(_search_cli.run(backend, argv) or 0)
            except SystemExit as exc:
                code = int(exc.code or 0)
        return buf.getvalue(), code

    def ledger_records(self, session: str) -> list[dict]:
        path = (self.state_dir / f"{session}.evidence.jsonl").resolve()
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_search_with_session_writes_seen_rows(self) -> None:
        self.start_session("bind-ok")
        backend = FakeBackend()
        out, code = self.run_cli(
            backend,
            ["search", "AI jobs", "--session", "bind-ok", "--state-dir", str(self.state_dir)],
        )
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["query"], "AI jobs")
        records = self.ledger_records("bind-ok")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "seen")
        self.assertEqual(records[0]["backend"], "Fake")
        self.assertEqual(records[0]["query"], "AI jobs")
        self.assertEqual(records[0]["url"], "https://publisher.org/item")
        self.assertEqual(records[0]["title"], "ok")
        self.assertIn("ts", records[0])

    def test_search_without_session_does_not_write_ledger(self) -> None:
        self.start_session("no-sess")
        backend = FakeBackend()
        out, code = self.run_cli(backend, ["search", "AI jobs", "--state-dir", str(self.state_dir)])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ledger_records("no-sess"), [])
        self.assertFalse((self.state_dir / "no-sess.evidence.jsonl").exists())

    def test_ledger_write_failure_is_nonzero_and_does_not_print_success(self) -> None:
        self.start_session("bind-fail")
        backend = FakeBackend()
        with mock.patch.object(evidence_mod, "append_seen_hits", side_effect=OSError("disk full")):
            out, code = self.run_cli(
                backend,
                ["search", "AI jobs", "--session", "bind-fail", "--state-dir", str(self.state_dir)],
            )
        self.assertNotEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("error", payload)
        self.assertIn("evidence ledger write failed", payload["error"])
        self.assertEqual(self.ledger_records("bind-fail"), [])

    def test_unknown_session_fails_closed(self) -> None:
        backend = FakeBackend()
        out, code = self.run_cli(
            backend,
            ["search", "AI jobs", "--session", "ghost", "--state-dir", str(self.state_dir)],
        )
        self.assertNotEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("evidence ledger write failed", payload["error"])
        self.assertIn("does not exist", payload["error"])

    def test_batch_search_with_session_writes_each_query(self) -> None:
        self.start_session("bind-batch")
        backend = FakeBackend()
        out, code = self.run_cli(
            backend,
            [
                "batch_search",
                "--query",
                "q1",
                "--query",
                "q2",
                "--session",
                "bind-batch",
                "--state-dir",
                str(self.state_dir),
            ],
        )
        self.assertEqual(code, 0, out)
        records = self.ledger_records("bind-batch")
        self.assertEqual(len(records), 2)
        self.assertEqual({r["query"] for r in records}, {"q1", "q2"})
        self.assertTrue(all(r["url"] == "https://publisher.org/item" for r in records))

    def test_empty_hits_with_session_succeed_without_ledger_file(self) -> None:
        self.start_session("bind-empty")
        backend = FakeBackend(results=[])
        out, code = self.run_cli(
            backend,
            ["search", "none", "--session", "bind-empty", "--state-dir", str(self.state_dir)],
        )
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ledger_records("bind-empty"), [])


class SeenRecordsFromHitsTests(unittest.TestCase):
    def test_accepts_url_or_link_and_skips_invalid(self) -> None:
        records = evidence_mod.seen_records_from_hits(
            "Exa",
            {
                "q": [
                    {"title": "A", "url": "https://a.example/x"},
                    {"title": "B", "link": "https://b.example/y"},
                    {"title": "bad", "url": "not-a-url"},
                    {"title": "empty"},
                ]
            },
        )
        self.assertEqual([r["url"] for r in records], ["https://a.example/x", "https://b.example/y"])
        self.assertEqual(records[0]["backend"], "Exa")
        self.assertEqual(records[1]["title"], "B")


class LedgerBindSharedHelperTests(unittest.TestCase):
    def test_serpapi_handlers_call_shared_helper_not_append_records(self) -> None:
        source = SERPAPI.read_text(encoding="utf-8")
        self.assertIn("bind_successful_search_to_ledger", source)
        self.assertNotIn("append_records", source)
        self.assertNotIn("append_seen_hits", source)

    def test_default_search_paths_call_shared_helper(self) -> None:
        source = (Path(__file__).parents[1] / "src" / "tri_research_runtime" / "search_cli.py").read_text(
            encoding="utf-8"
        )
        self.assertGreaterEqual(source.count("bind_successful_search_to_ledger("), 3)


if __name__ == "__main__":
    unittest.main()

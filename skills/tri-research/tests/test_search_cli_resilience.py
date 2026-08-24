"""Resilience contract for the shared search CLI skeleton.

Transient backend failures must be retried; hung calls must time out;
repeated exhausted failures must open a per-backend circuit so later
calls fail fast. JSON shapes and exit codes stay the existing contract.

Seam: `_search_cli.search` / `batch_search` / `check` with a FakeBackend
standing in for the external SDK. Tests do not reach private helpers.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _search_cli  # noqa: E402


class FakeBackend(_search_cli.Backend):
    name = "Fake"
    help = "Fake backend for resilience tests"
    sdk = object()
    missing_sdk_message = "fake-sdk not installed"
    env_key = "FAKE_SEARCH_KEY"
    client_factory = staticmethod(lambda key: object())
    flags = ()
    max_attempts = 3
    retry_backoff = 0.0
    call_timeout = 5.0
    circuit_threshold = 5
    circuit_cooldown = 60.0

    def __init__(self) -> None:
        self.calls = 0
        self.fail_times = 0
        self.hang = False
        self.release = threading.Event()
        self.error: Exception | None = ConnectionError("connection reset")

    def probe(self, client: object) -> bool:
        self.calls += 1
        if self.hang:
            self.release.wait()
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.error or ConnectionError("connection reset")
        return True

    def search(self, client: object, query: str, options: dict) -> dict:
        self.calls += 1
        if self.hang:
            self.release.wait()
            return {"results": []}
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.error or ConnectionError("connection reset")
        return {"results": [{"title": "ok", "url": "https://publisher.org/item"}]}


def _namespace(query: str) -> argparse.Namespace:
    return argparse.Namespace(query=query, command="search")


def _run_search(backend: FakeBackend, query: str = "q") -> tuple[dict, int]:
    buf = io.StringIO()
    code = 0
    with redirect_stdout(buf):
        try:
            _search_cli.search(backend, _namespace(query))
        except SystemExit as exc:
            code = int(exc.code or 0)
    return json.loads(buf.getvalue()), code


class SearchRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("FAKE_SEARCH_KEY")
        os.environ["FAKE_SEARCH_KEY"] = "test-key"

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("FAKE_SEARCH_KEY", None)
        else:
            os.environ["FAKE_SEARCH_KEY"] = self._old

    def test_search_retries_transient_error_then_succeeds(self) -> None:
        backend = FakeBackend()
        backend.fail_times = 2
        payload, code = _run_search(backend)
        self.assertEqual(code, 0)
        self.assertEqual(backend.calls, 3)
        self.assertEqual(payload["query"], "q")
        self.assertEqual(payload["results"][0]["title"], "ok")

    def test_search_exhausted_retries_keep_json_error_contract(self) -> None:
        backend = FakeBackend()
        backend.fail_times = 5
        payload, code = _run_search(backend)
        self.assertEqual(code, 1)
        self.assertEqual(backend.calls, 3)
        self.assertIn("error", payload)
        self.assertEqual(payload["query"], "q")

    def test_http_429_is_retried_then_succeeds(self) -> None:
        backend = FakeBackend()
        backend.error = RuntimeError("HTTP 429 Too Many Requests")
        backend.fail_times = 1
        payload, code = _run_search(backend)
        self.assertEqual(code, 0)
        self.assertEqual(backend.calls, 2)
        self.assertEqual(payload["results"][0]["title"], "ok")

    def test_http_400_is_not_retried(self) -> None:
        backend = FakeBackend()
        backend.error = RuntimeError("HTTP 400 Bad Request")
        backend.fail_times = 5
        payload, code = _run_search(backend)
        self.assertEqual(code, 1)
        self.assertEqual(backend.calls, 1)
        self.assertIn("HTTP 400", payload["error"])

    def test_missing_key_is_not_retried(self) -> None:
        os.environ.pop("FAKE_SEARCH_KEY", None)
        backend = FakeBackend()
        buf = io.StringIO()
        code = 0
        with redirect_stdout(buf):
            try:
                _search_cli.search(backend, _namespace("q"))
            except SystemExit as exc:
                code = int(exc.code or 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(backend.calls, 0)
        self.assertIn("FAKE_SEARCH_KEY", payload["error"])


class SearchTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FAKE_SEARCH_KEY"] = "test-key"

    def tearDown(self) -> None:
        os.environ.pop("FAKE_SEARCH_KEY", None)

    def test_hung_search_times_out_instead_of_hanging(self) -> None:
        backend = FakeBackend()
        backend.hang = True
        backend.call_timeout = 0.2
        backend.max_attempts = 1
        payload, code = _run_search(backend)
        self.assertEqual(code, 1)
        self.assertIn("error", payload)
        self.assertRegex(payload["error"].lower(), r"timeout|timed out")


class SearchCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FAKE_SEARCH_KEY"] = "test-key"

    def tearDown(self) -> None:
        os.environ.pop("FAKE_SEARCH_KEY", None)

    def test_open_circuit_fails_fast_without_calling_backend(self) -> None:
        backend = FakeBackend()
        backend.fail_times = 100
        backend.max_attempts = 2
        backend.circuit_threshold = 2
        _, code1 = _run_search(backend)
        _, code2 = _run_search(backend)
        self.assertEqual(code1, 1)
        self.assertEqual(code2, 1)
        self.assertEqual(backend.calls, 4)  # two exhausted searches × 2 attempts
        payload, code3 = _run_search(backend)
        self.assertEqual(code3, 1)
        self.assertEqual(backend.calls, 4)
        self.assertRegex(payload["error"].lower(), r"circuit")

    def test_successful_search_closes_circuit(self) -> None:
        backend = FakeBackend()
        backend.circuit_threshold = 1
        backend.max_attempts = 1
        backend.fail_times = 1
        _run_search(backend)  # opens circuit
        self.assertEqual(backend.calls, 1)
        backend.circuit_cooldown = 0.0  # allow half-open immediately
        backend.fail_times = 0
        payload, code = _run_search(backend)
        self.assertEqual(code, 0)
        self.assertEqual(payload["results"][0]["title"], "ok")
        backend.fail_times = 1
        _run_search(backend)
        # circuit was closed, so this search is attempted again
        self.assertEqual(backend.calls, 3)


class BatchSearchRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FAKE_SEARCH_KEY"] = "test-key"

    def tearDown(self) -> None:
        os.environ.pop("FAKE_SEARCH_KEY", None)

    def test_batch_retries_each_query_independently(self) -> None:
        backend = FakeBackend()
        backend.fail_times = 1  # first query fails once then succeeds; second succeeds
        args = argparse.Namespace(query=["one", "two"], command="batch_search")
        buf = io.StringIO()
        with redirect_stdout(buf):
            _search_cli.batch_search(backend, args)
        payload = json.loads(buf.getvalue())
        self.assertEqual(backend.calls, 3)
        self.assertIn("one", payload)
        self.assertIn("two", payload)
        self.assertIsInstance(payload["one"], list)
        self.assertIsInstance(payload["two"], list)


class CheckTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FAKE_SEARCH_KEY"] = "test-key"

    def tearDown(self) -> None:
        os.environ.pop("FAKE_SEARCH_KEY", None)

    def test_hung_probe_reports_unavailable_json(self) -> None:
        backend = FakeBackend()
        backend.hang = True
        backend.call_timeout = 0.2
        buf = io.StringIO()
        with redirect_stdout(buf):
            _search_cli.check(backend)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["available"])
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()

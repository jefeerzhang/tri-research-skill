"""Registry expand tests — seam is SearchBackendRegistry.search.

Ticket #6: Registry + SearchResult must be deep Module; tests exercise the
interface, not implementation details. FakeBackend stands in for SDK.
"""

from __future__ import annotations

import os
import threading
import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _search_cli  # noqa: E402
from _search_registry import KeyProvider, SearchBackendRegistry, SearchResult, clear_proxy_vars  # noqa: E402


class FakeBackend(_search_cli.Backend):
    name = "Fake"
    help = "Fake backend for registry tests"
    sdk = object()
    missing_sdk_message = "fake-sdk not installed"
    env_key = "FAKE_REGISTRY_KEY"
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
        # Include extra fields to test truncation & engine_meta
        return {
            "results": [
                {
                    "title": "ok",
                    "url": "https://publisher.org/item",
                    "snippet": "x" * 1000,
                    "content": "y" * 10000,
                    "score": 0.9,
                    "published_date": "2024-01-01",
                }
            ]
        }


def _registry_with_fake(**overrides) -> tuple[SearchBackendRegistry, FakeBackend]:
    reg = SearchBackendRegistry()
    fb = FakeBackend()
    for k, v in overrides.items():
        setattr(fb, k, v)
    from _search_registry import BackendSpec

    reg.register(BackendSpec(name="fake", backend=fb, env_key="FAKE_REGISTRY_KEY"))
    return reg, fb


class RegistryInterfaceTests(unittest.TestCase):
    def test_register_and_get_and_list(self) -> None:
        reg, _ = _registry_with_fake()
        self.assertIn("fake", reg.list_backends())
        spec = reg.get("fake")
        self.assertEqual(spec.name, "fake")

    def test_search_returns_search_result_list(self) -> None:
        os.environ["FAKE_REGISTRY_KEY"] = "k"
        try:
            reg, _ = _registry_with_fake()
            results = reg.search("fake", "q")
            self.assertEqual(len(results), 1)
            self.assertIsInstance(results[0], SearchResult)
            self.assertEqual(results[0].title, "ok")
            self.assertEqual(results[0].url, "https://publisher.org/item")
        finally:
            os.environ.pop("FAKE_REGISTRY_KEY", None)

    def test_truncation_is_uniform(self) -> None:
        os.environ["FAKE_REGISTRY_KEY"] = "k"
        try:
            reg, _ = _registry_with_fake()
            r = reg.search("fake", "q")[0]
            self.assertEqual(len(r.snippet), 500)
            self.assertEqual(len(r.content or ""), 5000)
        finally:
            os.environ.pop("FAKE_REGISTRY_KEY", None)


class RegistryRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FAKE_REGISTRY_KEY"] = "test-key"

    def tearDown(self) -> None:
        os.environ.pop("FAKE_REGISTRY_KEY", None)

    def test_search_retries_transient_then_succeeds(self) -> None:
        reg, fb = _registry_with_fake()
        fb.fail_times = 2
        results = reg.search("fake", "q")
        self.assertEqual(fb.calls, 3)
        self.assertEqual(results[0].title, "ok")

    def test_search_exhausted_raises(self) -> None:
        reg, fb = _registry_with_fake()
        fb.fail_times = 5
        with self.assertRaises(Exception) as ctx:
            reg.search("fake", "q")
        self.assertEqual(fb.calls, 3)
        self.assertIn("connection", str(ctx.exception).lower())

    def test_http_429_retried(self) -> None:
        reg, fb = _registry_with_fake()
        fb.error = RuntimeError("HTTP 429 Too Many Requests")
        fb.fail_times = 1
        results = reg.search("fake", "q")
        self.assertEqual(fb.calls, 2)
        self.assertEqual(results[0].title, "ok")

    def test_http_400_not_retried(self) -> None:
        reg, fb = _registry_with_fake()
        fb.error = RuntimeError("HTTP 400 Bad Request")
        fb.fail_times = 5
        with self.assertRaises(Exception) as ctx:
            reg.search("fake", "q")
        self.assertEqual(fb.calls, 1)
        self.assertIn("HTTP 400", str(ctx.exception))


class RegistryTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FAKE_REGISTRY_KEY"] = "k"

    def tearDown(self) -> None:
        os.environ.pop("FAKE_REGISTRY_KEY", None)

    def test_hung_search_times_out(self) -> None:
        reg, fb = _registry_with_fake(call_timeout=0.2, max_attempts=1)
        fb.hang = True
        with self.assertRaises(Exception) as ctx:
            reg.search("fake", "q")
        self.assertRegex(str(ctx.exception).lower(), r"timeout|timed out")


class RegistryCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FAKE_REGISTRY_KEY"] = "k"

    def tearDown(self) -> None:
        os.environ.pop("FAKE_REGISTRY_KEY", None)

    def test_open_circuit_fails_fast(self) -> None:
        reg, fb = _registry_with_fake(max_attempts=2, circuit_threshold=2)
        fb.fail_times = 100
        for _ in range(2):
            try:
                reg.search("fake", "q")
            except Exception:
                pass
        self.assertEqual(fb.calls, 4)
        with self.assertRaises(Exception) as ctx:
            reg.search("fake", "q")
        self.assertEqual(fb.calls, 4)
        self.assertRegex(str(ctx.exception).lower(), r"circuit")

    def test_success_closes_circuit(self) -> None:
        reg, fb = _registry_with_fake(max_attempts=1, circuit_threshold=1)
        fb.fail_times = 1
        try:
            reg.search("fake", "q")
        except Exception:
            pass
        fb.circuit_cooldown = 0.0
        fb.fail_times = 0
        results = reg.search("fake", "q")
        self.assertEqual(results[0].title, "ok")


class RegistryBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FAKE_REGISTRY_KEY"] = "k"

    def tearDown(self) -> None:
        os.environ.pop("FAKE_REGISTRY_KEY", None)

    def test_batch_retries_each_query_independently(self) -> None:
        reg, fb = _registry_with_fake()
        fb.fail_times = 1
        out = reg.batch_search("fake", ["one", "two"])
        self.assertEqual(fb.calls, 3)
        self.assertIsInstance(out["one"], list)
        self.assertIsInstance(out["two"], list)

    def test_batch_partial_failure_is_error_dict(self) -> None:
        # Make first query always fail, second succeed — requires per-query isolation
        reg = SearchBackendRegistry()

        class Flaky(FakeBackend):
            def search(self, client, query, options):
                self.calls += 1
                if query == "bad":
                    raise RuntimeError("HTTP 400 Bad Request")
                return {"results": [{"title": "ok", "url": "https://x"}]}

        flaky = Flaky()
        from _search_registry import BackendSpec

        reg.register(BackendSpec(name="flaky", backend=flaky, env_key="FAKE_REGISTRY_KEY"))
        out = reg.batch_search("flaky", ["bad", "good"])
        self.assertIn("error", out["bad"])  # type: ignore[typeddict-item]
        self.assertIsInstance(out["good"], list)


class RegistryCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FAKE_REGISTRY_KEY"] = "k"

    def tearDown(self) -> None:
        os.environ.pop("FAKE_REGISTRY_KEY", None)

    def test_hung_probe_reports_unavailable(self) -> None:
        reg, fb = _registry_with_fake(call_timeout=0.2)
        fb.hang = True
        payload = reg.check("fake")
        self.assertFalse(payload["available"])
        self.assertIn("error", payload)


class KeyProviderTests(unittest.TestCase):
    def test_priority_cli_over_env_over_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / ".env"
            env_file.write_text("FAKE_REGISTRY_KEY=file-key\n", encoding="utf-8")
            os.environ["FAKE_REGISTRY_KEY"] = "env-key"
            try:
                self.assertEqual(KeyProvider.resolve("cli-key", "FAKE_REGISTRY_KEY", env_file), "cli-key")
                self.assertEqual(KeyProvider.resolve(None, "FAKE_REGISTRY_KEY", env_file), "env-key")
                os.environ.pop("FAKE_REGISTRY_KEY", None)
                self.assertEqual(KeyProvider.resolve(None, "FAKE_REGISTRY_KEY", env_file), "file-key")
                self.assertIsNone(KeyProvider.resolve(None, "FAKE_REGISTRY_KEY", Path(td) / "missing"))
            finally:
                os.environ.pop("FAKE_REGISTRY_KEY", None)

    def test_no_proxy_clears_vars(self) -> None:
        os.environ["HTTP_PROXY"] = "http://proxy"
        os.environ["https_proxy"] = "http://proxy2"
        clear_proxy_vars()
        self.assertNotIn("HTTP_PROXY", os.environ)
        self.assertNotIn("https_proxy", os.environ)


if __name__ == "__main__":
    unittest.main()

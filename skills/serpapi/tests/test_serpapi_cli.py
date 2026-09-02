"""Regression tests for SerpApi .env parsing via KeyProvider.

Bug 1: a .env line `SERPAPI_KEY` with no `=` crashes load_key with
IndexError (split("=", 1)[1] on a single-element list).
Bug 2: a line `SERPAPI_KEY_EXTRA=foo` matches startswith("SERPAPI_KEY")
and its value is wrongly returned as THE key.

Both bugs lived in serpapi_cli's local `_key_from_env_file`, which
candidate 5 deleted: parsing now lives solely in
`_search_registry._key_from_env_file` (consumed via KeyProvider by
load_key). These tests pin the shared implementation from the consumer
side, keeping the historical bug coverage alive.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "serpapi_cli.py"
SPEC = importlib.util.spec_from_file_location("serpapi_cli", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

# serpapi_cli bootstrapped tri-research/scripts onto sys.path above, so the
# shared parser is importable here; serpapi's load_key delegates to it.
import _search_registry  # noqa: E402


class EnvFileKeyTests(unittest.TestCase):
    def _write_env(self, content: str) -> Path:
        path = Path(self.tmp.name) / ".env"
        path.write_text(content, encoding="utf-8")
        return path

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_line_without_equals_does_not_crash(self) -> None:
        env = self._write_env("SERPAPI_KEY\n")
        self.assertIsNone(_search_registry._key_from_env_file(env, "SERPAPI_KEY"))

    def test_prefixed_variable_is_not_matched(self) -> None:
        env = self._write_env("SERPAPI_KEY_EXTRA=not-the-key\n")
        self.assertIsNone(_search_registry._key_from_env_file(env, "SERPAPI_KEY"))

    def test_exact_key_is_read(self) -> None:
        env = self._write_env("SERPAPI_KEY=abc123\n")
        self.assertEqual(_search_registry._key_from_env_file(env, "SERPAPI_KEY"), "abc123")

    def test_quoted_value_is_unquoted(self) -> None:
        env = self._write_env('SERPAPI_KEY="quoted-value"\n')
        self.assertEqual(_search_registry._key_from_env_file(env, "SERPAPI_KEY"), "quoted-value")

    def test_missing_file_returns_none(self) -> None:
        self.assertIsNone(_search_registry._key_from_env_file(Path(self.tmp.name) / "nope.env", "SERPAPI_KEY"))


if __name__ == "__main__":
    unittest.main()


class SerpApiRetryTests(unittest.TestCase):
    def test_batch_search_retries_transient_network_error(self) -> None:
        import argparse
        import io
        from contextlib import redirect_stdout

        backend = MODULE.SerpApiBackend()
        backend.retry_backoff = 0.0
        backend.max_attempts = 3
        calls = {"n": 0}

        def flaky_fetch(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise MODULE.SerpApiError("Network error: connection reset\n", 3)
            return {"organic_results": [{"title": "ok", "link": "https://example.org"}]}

        original = MODULE._serpapi_fetch
        MODULE._serpapi_fetch = flaky_fetch
        try:
            args = argparse.Namespace(
                query=["q1"],
                engine="google",
                hl=None,
                gl=None,
                num=None,
                since=None,
                api_key="k",
                no_proxy=False,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                MODULE._serpapi_cmd_batch_search(backend, args)
            payload = json.loads(buf.getvalue())
        finally:
            MODULE._serpapi_fetch = original

        self.assertEqual(calls["n"], 2)
        self.assertIn("q1", payload)
        self.assertEqual(payload["q1"]["results"][0]["title"], "ok")

    def test_missing_key_is_not_retried(self) -> None:
        import argparse
        import io
        from contextlib import redirect_stdout

        backend = MODULE.SerpApiBackend()
        backend.retry_backoff = 0.0
        calls = {"n": 0}

        def missing_key(*_args, **_kwargs):
            calls["n"] += 1
            raise MODULE.SerpApiError("No SerpApi key found.\n", 1)

        original = MODULE._serpapi_fetch
        MODULE._serpapi_fetch = missing_key
        try:
            args = argparse.Namespace(
                query=["q1"],
                engine="google",
                hl=None,
                gl=None,
                num=None,
                since=None,
                api_key="k",
                no_proxy=False,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                MODULE._serpapi_cmd_batch_search(backend, args)
            payload = json.loads(buf.getvalue())
        finally:
            MODULE._serpapi_fetch = original

        self.assertEqual(calls["n"], 1)
        self.assertIn("No SerpApi key found", payload["q1"]["error"])

    def test_http_429_is_retried(self) -> None:
        import argparse
        import io
        from contextlib import redirect_stdout

        backend = MODULE.SerpApiBackend()
        backend.retry_backoff = 0.0
        calls = {"n": 0}

        def rate_limited(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise MODULE.SerpApiError("HTTP 429: rate limited\n", 4)
            return {"organic_results": [{"title": "ok", "link": "https://publisher.org"}]}

        original = MODULE._serpapi_fetch
        MODULE._serpapi_fetch = rate_limited
        try:
            args = argparse.Namespace(
                query=["q1"],
                engine="google",
                hl=None,
                gl=None,
                num=None,
                since=None,
                api_key="k",
                no_proxy=False,
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                MODULE._serpapi_cmd_batch_search(backend, args)
            payload = json.loads(buf.getvalue())
        finally:
            MODULE._serpapi_fetch = original

        self.assertEqual(calls["n"], 2)
        self.assertEqual(payload["q1"]["results"][0]["title"], "ok")


class SerpApiTimeoutSourceTests(unittest.TestCase):
    def test_backend_search_derives_requests_timeout_from_call_timeout(self) -> None:
        """Registry 路径（SerpApiBackend.search）的 requests 超时必须从 call_timeout 派生。

        Bug: CLI 路径（_serpapi_invoke_fetch）用 `int(backend.call_timeout or 60)`
        算 requests 超时，但 Registry 走的 backend.search 直接调 _serpapi_fetch 不传
        timeout，落到硬编码默认 60——调 call_timeout 只改了 CLI 一半，两条路不同源。
        """
        captured: dict = {}

        def fake_fetch(engine, query, hl, gl, num, api_key, since=None, timeout=60):
            captured["timeout"] = timeout
            return {"organic_results": []}

        backend = MODULE.SerpApiBackend()
        backend.call_timeout = 17.0
        original = MODULE._serpapi_fetch
        MODULE._serpapi_fetch = fake_fetch
        try:
            backend.search(MODULE._serpapi_make_client("k"), "q", {})
        finally:
            MODULE._serpapi_fetch = original
        self.assertEqual(captured["timeout"], 17)


class CliNoKeyTests(unittest.TestCase):
    def test_engines_does_not_require_api_key(self) -> None:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            MODULE._search_cli.run(MODULE.SERPAPI_BACKEND, ["engines"])
        self.assertIn("## General", buf.getvalue())

    def test_doc_does_not_require_api_key(self) -> None:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            MODULE._search_cli.run(MODULE.SERPAPI_BACKEND, ["doc"])
        self.assertIn("serpapi_cli.py", buf.getvalue())

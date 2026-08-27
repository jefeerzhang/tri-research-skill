"""Contract tests for the Managed Command seam (ADR-0002).

Seam: `_search_cli.Command(managed=True, ...)` + `_search_cli.run_managed_command`.
The skeleton owns proxy clearing, key resolution (KeyProvider, reads .env),
SDK-missing check, client build, invoke (timeout/retry/circuit), error-JSON
printing and exit codes. Managed bodies only declare the SDK call + result
normalization and return the print-ready object (or raise CommandError).

Pinned invariants:
- success output uses ensure_ascii=False; error output keeps the legacy
  default escaping and the per-command echo field (query / url);
- unmanaged (raw) commands keep receiving bare args — SerpApi's Command
  entries are byte-identical in contract;
- the three tri-research command bodies no longer hand-copy bootstrap glue.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _search_cli  # noqa: E402
from _test_helpers import load_module  # noqa: E402

ENV_KEY = "FAKE_MANAGED_KEY"


class FakeManagedBackend(_search_cli.Backend):
    name = "Fake"
    help = "Fake backend for managed-command tests"
    sdk = object()
    missing_sdk_message = "fake-sdk not installed"
    env_key = ENV_KEY
    client_factory = staticmethod(lambda key: {"built_with": key})
    flags = ()
    max_attempts = 3
    retry_backoff = 0.0
    call_timeout = 5.0

    def probe(self, client) -> bool:  # pragma: no cover - unused here
        return True

    def search(self, client, query, options):  # pragma: no cover - unused here
        return {"results": []}


def _managed_command(body, name="go", echo=lambda args: {"query": args.query}):
    return _search_cli.Command(name, "managed test command", lambda p: None, body, managed=True, echo=echo)


def _invoke_command(backend, command, argv_ns) -> tuple[str, int | None]:
    """Run the seam; return (stdout, exit_code_or_None)."""
    buf = io.StringIO()
    code: int | None = None
    with redirect_stdout(buf):
        try:
            _search_cli.run_managed_command(backend, command, argv_ns)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return buf.getvalue(), code


class ManagedCommandSkeletonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.saved_key = os.environ.get(ENV_KEY)
        os.environ[ENV_KEY] = "test-key"
        self.backend = FakeManagedBackend()

    def tearDown(self) -> None:
        if self.saved_key is None:
            os.environ.pop(ENV_KEY, None)
        else:
            os.environ[ENV_KEY] = self.saved_key

    def test_success_prints_body_return_verbatim(self) -> None:
        ns = argparse.Namespace(query="hello", command="go")
        out, code = _invoke_command(self.backend, _managed_command(lambda client, args: {"answer": "ok"}), ns)
        self.assertIsNone(code)
        self.assertEqual(json.loads(out), {"answer": "ok"})

    def test_body_receives_resolved_client(self) -> None:
        seen: dict = {}

        def body(client, args):
            seen["client"] = client
            return {"ok": True}

        ns = argparse.Namespace(query="hello", command="go")
        _invoke_command(self.backend, _managed_command(body), ns)
        self.assertEqual(seen["client"], {"built_with": "test-key"})

    def test_non_ascii_preserved_on_success(self) -> None:
        ns = argparse.Namespace(query="气候", command="go")
        out, _ = _invoke_command(self.backend, _managed_command(lambda client, args: {"文本": "中文"}), ns)
        self.assertIn("中文", out)  # ensure_ascii=False

    def test_missing_key_errors_with_echo_and_exit_1(self) -> None:
        os.environ.pop(ENV_KEY, None)
        ns = argparse.Namespace(query="hello", command="go")
        out, code = _invoke_command(self.backend, _managed_command(lambda client, args: {"never": 1}), ns)
        self.assertEqual(code, 1)
        parsed = json.loads(out)
        self.assertIn(ENV_KEY, parsed["error"])
        self.assertEqual(parsed["query"], "hello")

    def test_missing_sdk_errors_and_body_never_runs(self) -> None:
        self.backend.sdk = None
        called = {"n": 0}

        def body(client, args):
            called["n"] += 1
            return {}

        ns = argparse.Namespace(query="hello", command="go")
        out, code = _invoke_command(self.backend, _managed_command(body), ns)
        self.assertEqual(code, 1)
        self.assertEqual(called["n"], 0)  # sdk checked before client build
        self.assertEqual(json.loads(out)["error"], "fake-sdk not installed")

    def test_body_failure_becomes_json_error_not_traceback(self) -> None:
        def body(client, args):
            raise RuntimeError("boom")

        ns = argparse.Namespace(query="hello", command="go")
        out, code = _invoke_command(self.backend, _managed_command(body), ns)
        self.assertEqual(code, 1)
        parsed = json.loads(out)
        self.assertEqual(parsed, {"error": "boom", "query": "hello"})

    def test_error_output_keeps_legacy_bytes_level_contract(self) -> None:
        """Byte-exact: errors stay ASCII-escaped with ``error`` before the echo.

        Success output uses ensure_ascii=False, but the pre-refactor error
        literals had no such flag. Reserialising via json.loads would hide a
        reordering or an escaping change, so compare the raw line.
        """

        def body(client, args):
            raise RuntimeError("密钥失效")

        ns = argparse.Namespace(query="气候", command="go")
        out, code = _invoke_command(self.backend, _managed_command(body), ns)
        self.assertEqual(code, 1)
        self.assertEqual(
            out.strip(),
            '{"error": "\\u5bc6\\u94a5\\u5931\\u6548", "query": "\\u6c14\\u5019"}',
        )

    def test_missing_key_error_orders_error_before_echo(self) -> None:
        os.environ.pop(ENV_KEY, None)
        ns = argparse.Namespace(query="hello", command="go")
        out, code = _invoke_command(self.backend, _managed_command(lambda client, args: {"never": 1}), ns)
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), f'{{"error": "{ENV_KEY} not set", "query": "hello"}}')

    def test_command_error_is_not_retried(self) -> None:
        calls = {"n": 0}

        def body(client, args):
            calls["n"] += 1
            raise _search_cli.CommandError("no content extracted")

        ns = argparse.Namespace(query="hello", command="go")
        out, code = _invoke_command(self.backend, _managed_command(body), ns)
        self.assertEqual(code, 1)
        self.assertEqual(calls["n"], 1)  # domain errors must not burn retries
        self.assertEqual(json.loads(out)["error"], "no content extracted")

    def test_transient_error_is_retried_then_succeeds(self) -> None:
        calls = {"n": 0}

        def body(client, args):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("connection reset")
            return {"ok": True}

        ns = argparse.Namespace(query="hello", command="go")
        out, code = _invoke_command(self.backend, _managed_command(body), ns)
        self.assertIsNone(code)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(json.loads(out), {"ok": True})

    def test_proxy_cleared_before_key_resolution(self) -> None:
        os.environ["HTTP_PROXY"] = "http://proxy.invalid"
        ns = argparse.Namespace(query="hello", command="go", no_proxy=True)
        _invoke_command(self.backend, _managed_command(lambda client, args: {}), ns)
        self.assertNotIn("HTTP_PROXY", os.environ)

    def test_raw_command_still_receives_bare_args(self) -> None:
        """Unmanaged commands keep the old (args) contract — SerpApi is untouched."""
        seen: list = []
        raw = _search_cli.Command("doc", "raw", lambda p: None, lambda args: seen.append(args))
        self.assertFalse(raw.managed)
        backend = FakeManagedBackend()
        backend.commands = [raw]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = _search_cli.run(backend, ["doc"])
        self.assertEqual(rc, 0)
        self.assertEqual(seen[0].command, "doc")


class TriBackendsUseManagedCommandsTests(unittest.TestCase):
    """The three tri-research commands must be registered as managed,
    and their bodies must be pure 'SDK call + normalization'."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.backends = load_module(SCRIPT_DIR / "search_backends.py", "sb_managed_test")

    def commands_by_name(self, backend):
        return {c.name: c for c in backend.commands}

    def test_answer_contents_extract_registered_managed_with_echo(self) -> None:
        exa = self.commands_by_name(self.backends.EXA_BACKEND)
        tav = self.commands_by_name(self.backends.TAVILY_BACKEND)
        self.assertTrue(exa["answer"].managed and exa["contents"].managed)
        self.assertTrue(tav["extract"].managed)
        ns = argparse.Namespace(query="q", url="https://x.dev")
        self.assertEqual(exa["answer"].echo(ns), {"query": "q"})
        self.assertEqual(exa["contents"].echo(ns), {"url": "https://x.dev"})
        self.assertEqual(tav["extract"].echo(ns), {"url": "https://x.dev"})

    def test_bodies_do_not_hand_roll_bootstrap(self) -> None:
        """Drift gate: key/proxy/exit glue lives in the skeleton, not here."""
        source = (SCRIPT_DIR / "search_backends.py").read_text(encoding="utf-8")
        self.assertNotIn("KeyProvider", source)
        self.assertNotIn("os.environ.pop", source)
        self.assertNotIn("sys.exit", source)

    def test_answer_body_shapes_citations(self) -> None:
        class _Cit:
            title = "T"
            url = "U"
            text = "x" * 2000

        class _Resp:
            answer = "A"
            citations = [_Cit()]

        class _Client:
            def answer(self, query, text=False):
                return _Resp()

        body = self.commands_by_name(self.backends.EXA_BACKEND)["answer"].run
        out = body(_Client(), argparse.Namespace(query="q"))
        self.assertEqual(out["query"], "q")
        self.assertEqual(out["answer"], "A")
        self.assertEqual(len(out["citations"][0]["text"]), 1000)

    def test_contents_body_truncates_text(self) -> None:
        class _Page:
            url = "U"
            title = "T"
            text = "y" * 6000

        class _Client:
            def get_contents(self, urls):
                return type("R", (), {"results": [_Page()]})()

        body = self.commands_by_name(self.backends.EXA_BACKEND)["contents"].run
        out = body(_Client(), argparse.Namespace(url="https://x.dev"))
        self.assertIsInstance(out, list)  # success payload stays a bare list
        self.assertEqual(len(out[0]["text"]), 5000)

    def test_extract_body_raises_domain_error_when_empty(self) -> None:
        class _Client:
            def extract(self, urls, extract_depth=None):
                return {"results": []}

        body = self.commands_by_name(self.backends.TAVILY_BACKEND)["extract"].run
        with self.assertRaises(_search_cli.CommandError):
            body(_Client(), argparse.Namespace(url="https://x.dev", depth="advanced"))


if __name__ == "__main__":
    unittest.main()

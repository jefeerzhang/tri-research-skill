"""Contract tests for backend key resolution on the CLI path.

Bug: ``Backend.client()`` and ``_search_cli.check`` read the API key from
``os.environ`` only, while managed commands and SerpApi resolve through
KeyProvider (env + ``.env``). A key configured in ``.env`` made ``check``
report unavailable and ``search`` fail with "not set" — the probe lied
about what actually works. These tests pin that both paths delegate key
resolution to KeyProvider; the priority rules themselves (cli > env >
.env) are covered by the registry tests.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _search_cli  # noqa: E402
from _test_helpers import load_module  # noqa: E402

ENV_KEY = "FAKE_KEYPATH_KEY"


class _KeyBackend(_search_cli.Backend):
    name = "Fake"
    help = "Fake backend for key-resolution tests"
    sdk = object()
    missing_sdk_message = "fake-sdk not installed"
    env_key = ENV_KEY
    env_file = None  # explicit: undeclared backend resolves env-only
    client_factory = staticmethod(lambda key: {"key": key})
    flags = ()

    def probe(self, client) -> bool:
        return bool(client.get("key"))

    def search(self, client, query, options):  # pragma: no cover - unused here
        return {"results": []}


class BackendKeyResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = _KeyBackend()
        self.saved = os.environ.get(ENV_KEY)
        os.environ.pop(ENV_KEY, None)

    def tearDown(self) -> None:
        if self.saved is None:
            os.environ.pop(ENV_KEY, None)
        else:
            os.environ[ENV_KEY] = self.saved

    def _patch_resolve(self, value):
        from _search_registry import KeyProvider

        return mock.patch.object(KeyProvider, "resolve", return_value=value)

    def test_client_delegates_to_key_provider(self) -> None:
        with self._patch_resolve("k-from-envfile") as mocked:
            client = self.backend.client()
        self.assertEqual(client, {"key": "k-from-envfile"})
        mocked.assert_called_once_with(None, ENV_KEY, self.backend.env_file)

    def test_client_missing_everywhere_keeps_error_shape(self) -> None:
        buf = io.StringIO()
        with self._patch_resolve(None), redirect_stdout(buf):
            with self.assertRaises(SystemExit) as ctx:
                self.backend.client()
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(json.loads(buf.getvalue()), {"error": f"{ENV_KEY} not set"})

    def test_check_delegates_to_key_provider(self) -> None:
        with self._patch_resolve("k-from-envfile"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                _search_cli.check(self.backend)
        self.assertEqual(json.loads(buf.getvalue()), {"available": True})

    def test_check_missing_everywhere_reports_not_set(self) -> None:
        buf = io.StringIO()
        with self._patch_resolve(None), redirect_stdout(buf):
            _search_cli.check(self.backend)
        self.assertEqual(json.loads(buf.getvalue()), {"available": False, "error": f"{ENV_KEY} not set"})


class BackendEnvFileDeclarationTests(unittest.TestCase):
    """Backends declare their own .env location (ADR-0004).

    KeyProvider.resolve must not derive paths from any skill's directory
    name: each backend carries `env_file`, and the resolver only reads
    what it is handed. Replaces the pre-ADR sibling-path pin, which
    hard-coded the tri-research → serpapi layout inside KeyProvider.
    """

    def test_declared_env_file_is_honored_end_to_end(self) -> None:
        # No mocks: a declared .env must feed client() when env is empty.
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(f"{ENV_KEY}=k-from-declared-env\n", encoding="utf-8")
            backend = _KeyBackend()
            backend.env_file = env_file
            saved = os.environ.pop(ENV_KEY, None)
            try:
                self.assertEqual(backend.client(), {"key": "k-from-declared-env"})
            finally:
                if saved is not None:
                    os.environ[ENV_KEY] = saved

    def test_real_backends_declare_env_file(self) -> None:
        """Directory ownership pinned: each backend points at its OWN skill dir.

        A name-only assertion would let a parent-level regression (e.g.
        serpapi drifting to skills/.env) pass silently — the exact
        silent-.env-loss hazard ADR-0004 exists to kill.
        """
        backends = load_module(SCRIPT_DIR / "search_backends.py", "sb_envfile_test")
        tri_env = SCRIPT_DIR.parent / ".env"  # skills/tri-research/.env
        for backend in (backends.EXA_BACKEND, backends.TAVILY_BACKEND):
            self.assertEqual(backend.env_file, tri_env)
        serpapi = load_module(
            Path(__file__).parents[2] / "serpapi" / "scripts" / "serpapi_cli.py",
            "serpapi_envfile_test",
        )
        self.assertEqual(serpapi.SERPAPI_BACKEND.env_file, Path(__file__).parents[2] / "serpapi" / ".env")

    def test_key_provider_resolve_knows_no_layout(self) -> None:
        """Drift gate: the resolver must not derive paths from skill names."""
        import inspect

        import _search_registry as reg

        source = inspect.getsource(reg.KeyProvider.resolve)
        self.assertNotIn("serpapi", source.lower())
        self.assertNotIn("_script_dir", source.lower())


if __name__ == "__main__":
    unittest.main()

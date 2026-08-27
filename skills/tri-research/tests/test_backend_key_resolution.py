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

ENV_KEY = "FAKE_KEYPATH_KEY"


class _KeyBackend(_search_cli.Backend):
    name = "Fake"
    help = "Fake backend for key-resolution tests"
    sdk = object()
    missing_sdk_message = "fake-sdk not installed"
    env_key = ENV_KEY
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
        mocked.assert_called_once_with(None, ENV_KEY)

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


class KeyProviderSiblingEnvPathTests(unittest.TestCase):
    """The serpapi legacy candidate must point at skills/serpapi/.env.

    Regression: the candidate used one parent too many and landed on
    <root>/serpapi/.env, so `check` never saw the documented .env location
    while search (load_key) did — the probe lied for SerpApi too.
    """

    def test_resolve_finds_sibling_skill_env_file(self) -> None:
        import _search_registry as reg

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "skills" / "tri-research" / "scripts"
            scripts.mkdir(parents=True)
            serpapi_env = root / "skills" / "serpapi" / ".env"
            serpapi_env.parent.mkdir(parents=True)
            serpapi_env.write_text("SERPAPI_KEY=k-sibling\n", encoding="utf-8")
            saved = os.environ.pop("SERPAPI_KEY", None)
            try:
                with mock.patch.object(reg, "_SCRIPT_DIR", scripts):
                    self.assertEqual(reg.KeyProvider.resolve(None, "SERPAPI_KEY"), "k-sibling")
            finally:
                if saved is not None:
                    os.environ["SERPAPI_KEY"] = saved


if __name__ == "__main__":
    unittest.main()

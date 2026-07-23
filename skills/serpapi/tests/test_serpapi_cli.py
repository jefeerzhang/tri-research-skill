"""Regression tests for serpapi_cli.py .env parsing.

Bug 1: a .env line `SERPAPI_KEY` with no `=` crashes load_key with
IndexError (split("=", 1)[1] on a single-element list).
Bug 2: a line `SERPAPI_KEY_EXTRA=foo` matches startswith("SERPAPI_KEY")
and its value is wrongly returned as THE key.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "serpapi_cli.py"
SPEC = importlib.util.spec_from_file_location("serpapi_cli", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


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
        self.assertIsNone(MODULE._key_from_env_file(env))

    def test_prefixed_variable_is_not_matched(self) -> None:
        env = self._write_env("SERPAPI_KEY_EXTRA=not-the-key\n")
        self.assertIsNone(MODULE._key_from_env_file(env))

    def test_exact_key_is_read(self) -> None:
        env = self._write_env("SERPAPI_KEY=abc123\n")
        self.assertEqual(MODULE._key_from_env_file(env), "abc123")

    def test_quoted_value_is_unquoted(self) -> None:
        env = self._write_env('SERPAPI_KEY="quoted-value"\n')
        self.assertEqual(MODULE._key_from_env_file(env), "quoted-value")

    def test_missing_file_returns_none(self) -> None:
        self.assertIsNone(MODULE._key_from_env_file(Path(self.tmp.name) / "nope.env"))


if __name__ == "__main__":
    unittest.main()

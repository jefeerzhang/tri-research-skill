"""Required Backend gate (Exa + SciVerse K+S) — ADR-0006.

Seam: ``require_required_backends`` and ``StateStore.start_session`` behavior
when the gate fails (no session / active pointer written).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _test_helpers import load_module, patch_required_backends

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"


class RequiredBackendsGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rb = load_module(SCRIPTS_DIR / "required_backends.py", "required_backends_gate_test")

    def test_ready_when_keys_and_sdks_present(self) -> None:
        with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
            with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                self.rb.require_required_backends()  # does not raise

    def test_missing_exa_key_raises(self) -> None:
        def resolve(_cli, env_key, _env_file=None):
            return "k" if env_key == self.rb.SCIVERSE_ENV_KEY else None

        with mock.patch.object(self.rb.KeyProvider, "resolve", side_effect=resolve):
            with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                with self.assertRaises(self.rb.StateError) as ctx:
                    self.rb.require_required_backends()
        msg = str(ctx.exception)
        self.assertIn("EXA_API_KEY not set", msg)
        self.assertIn("dashboard.exa.ai", msg)

    def test_missing_sciverse_sdk_raises(self) -> None:
        def importable(name: str) -> bool:
            return name != self.rb.SCIVERSE_SDK

        with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
            with mock.patch.object(self.rb, "_sdk_importable", side_effect=importable):
                with self.assertRaises(self.rb.StateError) as ctx:
                    self.rb.require_required_backends()
        self.assertIn("sciverse SDK not installed", str(ctx.exception))
        self.assertIn("sciverse.space/docs#auth", str(ctx.exception))

    def test_lists_all_gaps_in_one_error(self) -> None:
        with mock.patch.object(self.rb.KeyProvider, "resolve", return_value=None):
            with mock.patch.object(self.rb, "_sdk_importable", return_value=False):
                with self.assertRaises(self.rb.StateError) as ctx:
                    self.rb.require_required_backends()
        msg = str(ctx.exception)
        self.assertIn("EXA_API_KEY not set", msg)
        self.assertIn("exa_py SDK not installed", msg)
        self.assertIn("SCIVERSE_API_TOKEN not set", msg)
        self.assertIn("sciverse SDK not installed", msg)


class StartSessionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sm = load_module(SCRIPTS_DIR / "state_machine.py", "sm_required_gate_test")
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.state_dir = Path(self.tmp.name) / "state"
        self.store = self.sm.StateStore(self.state_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_start_fails_without_writing_session(self) -> None:
        with mock.patch.object(
            self.sm,
            "require_required_backends",
            side_effect=self.sm.StateError("required backends not ready: test"),
        ):
            with self.assertRaises(self.sm.StateError):
                self.store.start_session("blocked")
        self.assertFalse((self.state_dir / "blocked.json").exists())
        self.assertFalse((self.state_dir / "active-session").exists())

    def test_start_succeeds_when_gate_patched(self) -> None:
        with patch_required_backends(self.sm):
            data = self.store.start_session("ok-session")
        self.assertEqual(data["phase"], "STARTED")
        self.assertTrue((self.state_dir / "ok-session.json").exists())


if __name__ == "__main__":
    unittest.main()

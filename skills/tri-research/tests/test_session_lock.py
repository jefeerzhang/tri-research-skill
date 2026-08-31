"""Seam: session_lock — lock timeout must surface as StateError.

On Windows the lock path polls msvcrt.LK_NBLCK. If the wait expires before
the lock is acquired, the context manager must raise StateError (CLI prints
ERROR: and exits 1). Unlocking a never-held region raises OSError and must
not swallow the timeout StateError.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _test_helpers import load_module

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"


class _AlwaysBlockedMsvcrt:
    """Stand-in for msvcrt: never grants LK_NBLCK; UNLCK of unheld raises."""

    LK_NBLCK = 1
    LK_UNLCK = 2

    def __init__(self) -> None:
        self.held = False

    def locking(self, _fd: int, mode: int, _nbytes: int) -> None:
        if mode == self.LK_NBLCK:
            raise OSError("lock held by another process")
        if mode == self.LK_UNLCK:
            if not self.held:
                raise OSError("Unlock of unlocked region")
            self.held = False
            return
        raise AssertionError(f"unexpected locking mode: {mode}")


class SessionLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sm = load_module(SCRIPTS_DIR / "state_machine.py", "sm_session_lock_test")

    def test_timeout_raises_state_error_not_unlock_oserror(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock_path = Path(tmp) / "s.lock"
            fake = _AlwaysBlockedMsvcrt()
            with mock.patch.object(self.sm, "fcntl", None):
                with mock.patch.object(self.sm, "msvcrt", fake, create=True):
                    with mock.patch.object(self.sm, "LOCK_WAIT_SECONDS", 0.05):
                        with mock.patch.object(self.sm, "LOCK_POLL_SECONDS", 0.01):
                            with self.assertRaises(self.sm.StateError) as ctx:
                                with self.sm.session_lock(lock_path):
                                    pass
            self.assertIn("timed out waiting for state lock", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

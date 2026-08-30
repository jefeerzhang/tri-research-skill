from __future__ import annotations

import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "state_machine.sh"


class ShellWrapperTests(unittest.TestCase):
    def test_state_machine_wrapper_uses_unix_line_endings(self) -> None:
        content = SCRIPT.read_bytes()
        self.assertNotIn(
            b"\r\n",
            content,
            "bash wrapper must use LF line endings on Windows Git Bash",
        )


if __name__ == "__main__":
    unittest.main()

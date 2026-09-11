"""KeyProvider — cli > env > .env seam (ADR-0004 / ADR-0015).

Layout knowledge lives with each ``Backend.env_file``. This module never
names a skill directory.
"""

from __future__ import annotations

import os
from pathlib import Path


def key_from_env_file(env_path: Path, env_key: str) -> str | None:
    """Read ``env_key`` from a dotenv-style file; missing file is not an error."""
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, value = line.partition("=")
                if sep and key.strip() == env_key:
                    return value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


class KeyProvider:
    """Resolve API key with priority cli > env > the caller-declared .env.

    Per spec C1 grill; the .env location is handed in by the caller
    (``Backend.env_file``) — layout knowledge lives with each backend,
    not here (ADR-0004).
    """

    @staticmethod
    def resolve(
        cli_key: str | None,
        env_key: str,
        env_file: Path | None = None,
    ) -> str | None:
        if cli_key:
            return cli_key
        env = os.environ.get(env_key)
        if env:
            return env
        # The caller declares where its own .env lives (Backend.env_file);
        # this module knows nothing about any skill's directory layout
        # (ADR-0004).
        if env_file is not None:
            v = key_from_env_file(env_file, env_key)
            if v:
                return v
        return None

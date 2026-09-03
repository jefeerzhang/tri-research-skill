#!/usr/bin/env python3
"""Required Backend gate: Exa + SciVerse must be ready before a Research Session starts.

K+S check (no network probe): Key resolvable via KeyProvider, and the SDK
importable. Called from ``StateStore.start_session`` (ADR-0006). No user/env
escape hatch — tests patch this module's ``require_required_backends`` or
supply stub SDKs + keys.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _common import StateError  # noqa: E402
from _search_registry import KeyProvider  # noqa: E402

EXA_ENV_KEY = "EXA_API_KEY"
EXA_ENV_FILE = _SCRIPT_DIR.parent / ".env"
EXA_SDK = "exa_py"
EXA_APPLY = "https://dashboard.exa.ai/api-keys"
EXA_VERIFY = "python scripts/exa_search.py check"

SCIVERSE_ENV_KEY = "SCIVERSE_API_TOKEN"
SCIVERSE_SDK = "sciverse"
SCIVERSE_APPLY = "https://sciverse.space/docs#auth"
SCIVERSE_VERIFY = 'python -c "from sciverse import AgentToolsClient; print(\'ok\')"'


def _sdk_importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _sciverse_env_file() -> Path | None:
    home = os.environ.get("SCIVERSE_HOME")
    if not home:
        return None
    return Path(home).expanduser() / ".env"


def _collect_gaps() -> list[str]:
    gaps: list[str] = []
    if not KeyProvider.resolve(None, EXA_ENV_KEY, EXA_ENV_FILE):
        gaps.append(f"Exa: {EXA_ENV_KEY} not set")
    if not _sdk_importable(EXA_SDK):
        gaps.append(f"Exa: {EXA_SDK} SDK not installed")
    if not KeyProvider.resolve(None, SCIVERSE_ENV_KEY, _sciverse_env_file()):
        gaps.append(f"SciVerse: {SCIVERSE_ENV_KEY} not set")
    if not _sdk_importable(SCIVERSE_SDK):
        gaps.append(f"SciVerse: {SCIVERSE_SDK} SDK not installed")
    return gaps


def require_required_backends() -> None:
    """Raise StateError if Exa or SciVerse are not K+S ready."""
    gaps = _collect_gaps()
    if not gaps:
        return
    detail = "; ".join(gaps)
    guide = (
        f"Configure before start — "
        f"Exa: pip install exa-py && export {EXA_ENV_KEY}=<key> ({EXA_APPLY}), verify: {EXA_VERIFY}; "
        f"SciVerse: pip install sciverse && export {SCIVERSE_ENV_KEY}=<token> ({SCIVERSE_APPLY}), "
        f"verify: {SCIVERSE_VERIFY}"
    )
    raise StateError(f"required backends not ready: {detail}. {guide}")

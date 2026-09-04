#!/usr/bin/env python3
"""Required Backend gate: Exa + SciVerse (K+S) and SerpApi (Key + probe) must be
ready before a Research Session starts.

- Exa / SciVerse: K+S check — Key resolvable via KeyProvider, and the SDK
  importable. No network probe (ADR-0006).
- SerpApi: Key resolvable via KeyProvider **plus** a lightweight live probe
  (reuse ``SerpApiBackend.probe``). This narrowly reopens ADR-0006's rejection
  of a start-time network probe for SerpApi only (see the ADR that evolves it).

Called from ``StateStore.start_session``. No user/env escape hatch — tests patch
this module's ``require_required_backends`` or supply stub SDKs + keys (for
SerpApi, a stub ``requests`` on PYTHONPATH so the probe passes offline).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# SerpApi lives in the sibling skill; the gate imports its Backend lazily so the
# probe reuses the exact same code path as ``serpapi_cli.py check``.
_SERPAPI_SCRIPTS = _SCRIPT_DIR.parents[1] / "serpapi" / "scripts"

from _common import StateError  # noqa: E402
from _search_cli import _run_with_timeout  # noqa: E402
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

SERPAPI_ENV_KEY = "SERPAPI_KEY"
SERPAPI_APPLY = "https://serpapi.com/dashboard"
SERPAPI_VERIFY = "python skills/serpapi/scripts/serpapi_cli.py check"

_serpapi_backend = None  # cached lazily so tests can patch the getter


def _sdk_importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _sciverse_env_file() -> Path | None:
    home = os.environ.get("SCIVERSE_HOME")
    if not home:
        return None
    return Path(home).expanduser() / ".env"


def _get_serpapi_backend():
    """Return the SerpApiBackend, importing the sibling skill lazily.

    Tests patch this getter to inject a fake backend, so ``serpapi_cli`` is never
    imported / hits the network in the default suite.
    """
    global _serpapi_backend
    if _serpapi_backend is None:
        if str(_SERPAPI_SCRIPTS) not in sys.path:
            sys.path.insert(0, str(_SERPAPI_SCRIPTS))
        import serpapi_cli  # noqa: E402

        _serpapi_backend = serpapi_cli.SERPAPI_BACKEND
    return _serpapi_backend


def _serpapi_gap() -> str | None:
    """Return a gap string if SerpApi is not Key + probe ready, else None."""
    backend = _get_serpapi_backend()
    key = KeyProvider.resolve(None, SERPAPI_ENV_KEY, backend.env_file)
    if not key:
        return f"SerpApi: {SERPAPI_ENV_KEY} not set"
    if backend.sdk is None:
        return f"SerpApi: {backend.missing_sdk_message}"
    try:
        # Wrap in the shared timeout helper so the probe runs under the same
        # timeout semantics as ``_search_cli.check`` / ``REGISTRY.check``
        # (Windows has no SIGALRM; the requests timeout alone is not enough).
        ok = _run_with_timeout(lambda: backend.probe(backend.client_factory(key)), backend.call_timeout)
    except Exception as exc:  # noqa: BLE001 — probe failure surfaces as a gap
        return f"SerpApi: probe failed: {exc}"
    if not ok:
        return "SerpApi: probe failed"
    return None


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
    serpapi_gap = _serpapi_gap()
    if serpapi_gap:
        gaps.append(serpapi_gap)
    return gaps


def require_required_backends() -> None:
    """Raise StateError if Exa / SciVerse (K+S) or SerpApi (Key + probe) not ready."""
    gaps = _collect_gaps()
    if not gaps:
        return
    detail = "; ".join(gaps)
    guide = (
        f"Configure before start — "
        f"Exa: pip install exa-py && export {EXA_ENV_KEY}=<key> ({EXA_APPLY}), verify: {EXA_VERIFY}; "
        f"SciVerse: pip install sciverse && export {SCIVERSE_ENV_KEY}=<token> ({SCIVERSE_APPLY}), "
        f"verify: {SCIVERSE_VERIFY}; "
        f"SerpApi: export {SERPAPI_ENV_KEY}=<key> ({SERPAPI_APPLY}), verify: {SERPAPI_VERIFY}"
    )
    raise StateError(f"required backends not ready: {detail}. {guide}")

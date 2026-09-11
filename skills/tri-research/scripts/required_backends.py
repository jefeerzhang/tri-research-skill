#!/usr/bin/env python3
"""Required Backend gate: walk ``requirement=required`` descriptors before start.

Machine Web Backends (Exa / Tavily / SerpApi) declare ``requirement`` and
``readiness()`` on ``Backend``. SciVerse is an academic SDK path, not a Web
Backend: it is a ``SciVerseReadiness`` descriptor on the **same** list, and
must not be registered into ``SearchBackendRegistry`` (ADR-0006).

- Exa: K+S via ``Backend.client()`` (same assembly as every other lane).
- SciVerse: K+S via KeyProvider + SDK import (no client to assemble).
- SerpApi: ``client()`` plus ``start_probe`` (ADR-0007 narrow exception).
- Tavily stays ``optional``; AnySearch ``recommended`` stays documentation-only.

Called from ``StateStore.start_session``. No user/env escape hatch — tests
patch this module's ``require_required_backends`` or supply stub SDKs + keys
(for SerpApi, a stub ``requests`` on PYTHONPATH so the probe passes offline).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Protocol

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# SerpApi lives in the sibling skill; the gate imports its Backend lazily so the
# probe reuses the exact same code path as ``serpapi_cli.py check``.
_SERPAPI_SCRIPTS = _SCRIPT_DIR.parents[1] / "serpapi" / "scripts"

from _common import StateError  # noqa: E402
from _search_cli import BackendRequirementLevel  # noqa: E402
from _search_registry import KeyProvider  # noqa: E402

_serpapi_backend = None  # cached lazily so tests can patch the getter


class ReadinessDescriptor(Protocol):
    """Shared surface for Machine backends and SciVerseReadiness."""

    name: str
    requirement: BackendRequirementLevel
    apply_url: str
    verify_cmd: str
    configure_hint: str

    def readiness(self) -> list[str]: ...


class SciVerseReadiness:
    """Academic-SDK readiness; not a Web Backend (ADR-0006 / ADR-0011)."""

    name = "SciVerse"
    requirement = BackendRequirementLevel.REQUIRED
    env_key = "SCIVERSE_API_TOKEN"
    sdk_module = "sciverse"
    apply_url = "https://sciverse.space/docs#auth"
    verify_cmd = "python -c \"from sciverse import AgentToolsClient; print('ok')\""
    configure_hint = (
        f"pip install sciverse && export {env_key}=<token> ({apply_url})"
    )

    def readiness(self) -> list[str]:
        gaps: list[str] = []
        if not KeyProvider.resolve(None, self.env_key, _sciverse_env_file()):
            gaps.append(f"{self.name}: {self.env_key} not set")
        if not _sdk_importable(self.sdk_module):
            gaps.append(f"{self.name}: {self.sdk_module} SDK not installed")
        return gaps


SCIVERSE_READINESS = SciVerseReadiness()

# Aliases so older tests can name env keys; canonical homes are the descriptors.
EXA_ENV_KEY = "EXA_API_KEY"
SCIVERSE_ENV_KEY = SCIVERSE_READINESS.env_key
SCIVERSE_SDK = SCIVERSE_READINESS.sdk_module
SERPAPI_ENV_KEY = "SERPAPI_KEY"


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


def _machine_backends():
    from search_backends import EXA_BACKEND, TAVILY_BACKEND

    return (EXA_BACKEND, TAVILY_BACKEND, _get_serpapi_backend())


def iter_readiness_descriptors() -> tuple[ReadinessDescriptor, ...]:
    """Machine Web Backends + SciVerseReadiness, in one iteration list."""
    return (*_machine_backends(), SCIVERSE_READINESS)


def iter_required_descriptors() -> tuple[ReadinessDescriptor, ...]:
    return tuple(
        d for d in iter_readiness_descriptors() if d.requirement == BackendRequirementLevel.REQUIRED
    )


def _guide(descriptors: tuple[ReadinessDescriptor, ...]) -> str:
    parts = [f"{d.name}: {d.configure_hint}, verify: {d.verify_cmd}" for d in descriptors]
    return "Configure before start — " + "; ".join(parts)


def require_required_backends() -> None:
    """Raise StateError if any required descriptor reports a readiness gap."""
    required = iter_required_descriptors()
    gaps: list[str] = []
    for descriptor in required:
        gaps.extend(descriptor.readiness())
    if not gaps:
        return
    detail = "; ".join(gaps)
    raise StateError(f"required backends not ready: {detail}. {_guide(required)}")

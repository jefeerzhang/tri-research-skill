"""Shared Machine Backend runtime for tri-research and serpapi (ADR-0015).

Install: ``pip install -e .`` from the repo root (``npx skills add`` does
not install this wheel). Without pip, the tri-research skill ships the
package under ``src/tri_research_runtime``; serpapi locates that sibling
``src/`` when the import is missing.
"""

from __future__ import annotations

from tri_research_runtime.errors import (
    CircuitOpenError,
    ClientSetupError,
    CommandError,
    KeyMissing,
    SdkMissing,
    StateError,
)
from tri_research_runtime.key_provider import KeyProvider, key_from_env_file
from tri_research_runtime.search_cli import (
    CITATION_TEXT_LIMIT,
    CONTENT_LIMIT,
    EXTRACT_CONTENT_LIMIT,
    SNIPPET_LIMIT,
    Backend,
    BackendRequirementLevel,
    Command,
    Flag,
    invoke,
    run,
    truncate,
)

__all__ = (
    "Backend",
    "BackendRequirementLevel",
    "CITATION_TEXT_LIMIT",
    "CONTENT_LIMIT",
    "CircuitOpenError",
    "ClientSetupError",
    "Command",
    "CommandError",
    "EXTRACT_CONTENT_LIMIT",
    "Flag",
    "KeyMissing",
    "KeyProvider",
    "SNIPPET_LIMIT",
    "SdkMissing",
    "StateError",
    "invoke",
    "key_from_env_file",
    "run",
    "truncate",
)

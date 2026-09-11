"""Compatibility shim: implementation lives in ``tri_research_runtime.search_cli``.

``python scripts/*.py`` and existing ``import _search_cli`` keep working
without ``pip install``. Canonical types and limits are in the package
(ADR-0015).
"""

from __future__ import annotations

import _runtime  # noqa: F401  — puts src/ on sys.path

from tri_research_runtime.search_cli import *  # noqa: F403
from tri_research_runtime.search_cli import (  # noqa: F401 — explicit for grep/gates
    CITATION_TEXT_LIMIT,
    CONTENT_LIMIT,
    EXTRACT_CONTENT_LIMIT,
    SNIPPET_LIMIT,
    Backend,
    BackendRequirementLevel,
    CircuitOpenError,
    ClientSetupError,
    Command,
    CommandError,
    Flag,
    KeyMissing,
    SdkMissing,
    bind_successful_search_to_ledger,
    check,
    clear_proxy_vars,
    invoke,
    json_error,
    run,
    run_managed_command,
    run_with_timeout,
    search,
    truncate,
    wants_no_proxy,
)

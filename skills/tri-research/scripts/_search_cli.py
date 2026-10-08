"""Compatibility shim: implementation lives in ``tri_research_runtime.search_cli``.

``python scripts/*.py`` and existing ``import _search_cli`` keep working
without ``pip install``. Canonical types and limits are in the package
(ADR-0015).

This file has two jobs and no more: put ``src/`` on ``sys.path`` for the no-pip
lane, then hand the package's interface over. The interface has exactly one home
— ``tri_research_runtime.search_cli.__all__`` (架构审查候选 7).

It used to declare that interface a second time by hand, right below the star
import. Two declarations, neither authoritative, and the hand-written one had
already drifted: ``batch_search`` was called from three places but missing from
the list, so it only worked because the star import leaked everything anyway.
"""

from __future__ import annotations

import _runtime  # noqa: F401  — puts src/ on sys.path

from tri_research_runtime.search_cli import *  # noqa: F403  — surface is the package's __all__

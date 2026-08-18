#!/usr/bin/env python3
"""SerpApi CLI wrapper (thin entry over the shared search-backend module).

The SerpApi backend is declared in `skills/tri-research/scripts/search_backends.py`;
this file keeps the existing command path and test seam stable.
"""
from __future__ import annotations

import sys
from pathlib import Path

_TRI_RESEARCH_SCRIPTS = Path(__file__).resolve().parents[2] / "tri-research" / "scripts"
if str(_TRI_RESEARCH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TRI_RESEARCH_SCRIPTS))

import _search_cli  # noqa: E402
from search_backends import (  # noqa: E402
    SERPAPI_BACKEND,
    SERPAPI_ENGINES,
    SerpApiBackend,
    SerpApiError,
    _key_from_env_file,
    build_tbs,
    clear_proxy_vars,
    load_key,
)


def main(argv: list[str] | None = None) -> int:
    return _search_cli.run(SERPAPI_BACKEND, argv)


if __name__ == "__main__":
    raise SystemExit(main())

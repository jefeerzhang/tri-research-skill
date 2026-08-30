#!/usr/bin/env python3
"""Tavily search wrapper for tri-research (thin CLI entry).

Backend declaration and logic live in `search_backends.py`; this file
keeps the existing command path and test seam stable.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import _search_cli  # noqa: E402
from search_backends import TAVILY_BACKEND  # noqa: E402

backend = TAVILY_BACKEND


def main(argv: list[str] | None = None) -> int:
    return _search_cli.run(backend, argv)


if __name__ == "__main__":
    raise SystemExit(main())

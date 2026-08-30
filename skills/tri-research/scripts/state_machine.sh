#!/usr/bin/env bash
# Compat wrapper that forwards to the canonical Python implementation.
# Usage: scripts/state_machine.sh --session <id> <command> [args...]
# See scripts/state_machine.py for the full interface.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Explicit override wins.
if [ -n "${PYTHON_BIN:-}" ] && [ -x "${PYTHON_BIN}" ]; then
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/state_machine.py" "$@"
fi

# 2. Standard names on PATH (python3/python/py; py.exe covers all Windows
#    installs made by the official installer).
for candidate in python3 python py; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        exec "${candidate}" "${SCRIPT_DIR}/state_machine.py" "$@"
    fi
done

echo "ERROR:no Python interpreter found. Set PYTHON_BIN or add python3/python/py to PATH." >&2
exit 127
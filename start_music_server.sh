#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Prefer uv if available; otherwise use the active venv's Python.
if command -v uv >/dev/null 2>&1; then
  exec uv run python run.py
else
  exec python run.py
fi

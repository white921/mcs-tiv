#!/usr/bin/env bash
# Create the Python environment used by the SUMO experiment scripts.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"

if ! command -v "$python_bin" >/dev/null 2>&1; then
    echo "Python interpreter not found: $python_bin" >&2
    exit 1
fi

"$python_bin" -m venv "$repo_root/.venv"
"$repo_root/.venv/bin/python" -m pip install --upgrade pip
"$repo_root/.venv/bin/python" -m pip install -r "$repo_root/requirements.txt"

if [ ! -x "$repo_root/.venv/bin/sumo" ]; then
    echo "SUMO 1.20.0 was not installed into the virtual environment." >&2
    exit 1
fi

echo "Setup complete. Use scripts/run_sumo.sh to start an experiment."

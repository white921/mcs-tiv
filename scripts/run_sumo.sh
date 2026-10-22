#!/usr/bin/env bash
# Run a scenario with this repository's virtual environment and SUMO tools.
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <scenario.py> [scenario arguments...]" >&2
    exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scenario="$1"
shift

case "$scenario" in
    /*) scenario_path="$scenario" ;;
    *) scenario_path="$repo_root/$scenario" ;;
esac

if [ ! -f "$scenario_path" ]; then
    echo "Scenario not found: $scenario_path" >&2
    exit 2
fi
if [ ! -x "$repo_root/.venv/bin/python" ]; then
    echo "Virtual environment is missing. Run: bash scripts/setup.sh" >&2
    exit 2
fi

default_sumo_home="$("$repo_root/.venv/bin/python" -c 'import sumo; from pathlib import Path; print(Path(sumo.__file__).resolve().parent)')"
# Do not inherit a system-wide SUMO_HOME: reproducibility requires 1.20.0.
# MCS_TIV_SUMO_HOME is an explicit escape hatch for a separately installed 1.20.0.
export SUMO_HOME="${MCS_TIV_SUMO_HOME:-$default_sumo_home}"
if [ ! -d "$SUMO_HOME/tools" ]; then
    echo "SUMO tools not found under SUMO_HOME=$SUMO_HOME" >&2
    exit 2
fi
export PATH="$SUMO_HOME/bin:$PATH"
export MPLBACKEND="${MPLBACKEND:-Agg}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-$repo_root/.cache/matplotlib}"
mkdir -p "$MPLCONFIGDIR"

scenario_dir="$(cd "$(dirname "$scenario_path")" && pwd)"
scenario_name="$(basename "$scenario_path")"
cd "$scenario_dir"
exec "$repo_root/.venv/bin/python" "$scenario_name" "$@"

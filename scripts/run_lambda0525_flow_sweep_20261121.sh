#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 PYTHON SUMO_HOME WORKTREE_PARENT" >&2
  exit 2
fi

python_bin=$1
sumo_home=$2
worktree_parent=$3

run_flow() {
  local flow=$1
  local workers=$2
  local seed_tag=$3
  shift 3
  local -a seeds=("$@")
  local worktree="${worktree_parent}/mcs-tiv-normalized-convex-lambda0525-r${flow}-600s-20261121"
  local run_name="normalized-convex-lambda0525-eval7-r${flow}-a1000-seeds${seed_tag}-600s-20261121"
  local output="${worktree}/results/runs/${run_name}"

  if [[ ! -x "$python_bin" ]]; then
    echo "python is not executable: $python_bin" >&2
    exit 2
  fi
  if [[ ! -d "$sumo_home" ]]; then
    echo "SUMO_HOME does not exist: $sumo_home" >&2
    exit 2
  fi
  if [[ ! -d "$worktree/.git" && ! -f "$worktree/.git" ]]; then
    echo "worktree does not exist: $worktree" >&2
    exit 2
  fi
  if [[ -n "$(git -C "$worktree" status --porcelain)" ]]; then
    echo "worktree is not clean: $worktree" >&2
    exit 2
  fi
  if [[ -e "$output" ]]; then
    echo "output already exists: $output" >&2
    exit 2
  fi

  "$python_bin" "$worktree/scripts/run_thesis_batch.py" \
    --sumo-home "$sumo_home" \
    --python "$python_bin" \
    --output "$output" \
    --cases eval7 \
    --seeds "${seeds[@]}" \
    --duration 600 \
    --eval7-flows "$flow" 1000 \
    --fixed-input-override "fixed_inputs/thesis/eval7-flow-sweep/requesting-${flow}-accepting-1000/seed-{seed}.jsonl" \
    --bus-allocation fixed \
    --workers "$workers" \
    --deceleration-active \
    --deceleration-convex-lambda 0.525 \
    --diagnostic-traces \
    --checkpoint-interval 60
}

# Standard multi-condition order: finish each ratio before starting the next.
run_flow 300 10 33-42 33 34 35 36 37 38 39 40 41 42
run_flow 500 5 43-47 43 44 45 46 47
run_flow 700 10 33-42 33 34 35 36 37 38 39 40 41 42
run_flow 1200 10 33-42 33 34 35 36 37 38 39 40 41 42

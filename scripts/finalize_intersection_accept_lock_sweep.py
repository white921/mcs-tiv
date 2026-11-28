#!/usr/bin/env python3
"""Validate and summarize the intermediate Accept-lock timing sweep."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics

from finalize_intersection_decision_lock_cadence_ablation import (
    BASELINE_SOURCE,
    bootstrap_mean_ci,
    collect,
    load_json,
    require,
)
from run_intersection_accept_lock_sweep import ACCEPT_LOCKS_S


METRIC_FIELDS = ("mean_speed_mps", "stop_time_s", "hard_brake_time_s")
EVENT_FIELDS = (
    "attempts", "evaluated", "unsupported", "started", "decisions",
    "accepts", "rejects", "applied", "waiting_for_agreement",
    "cancellations", "deferred", "duplicate_suppressed",
)


def lock_label(value: float) -> str:
    return str(value).replace(".", "p")


def sweep_roots(root: Path, accept_lock_s: float) -> list[Path]:
    arm = root / f"accept-lock-{lock_label(accept_lock_s)}s"
    require(arm.is_dir(), f"Accept-lock arm missing: {arm}")
    roots = sorted(
        path for path in arm.iterdir()
        if path.is_dir() and (path / "experiment-manifest.json").is_file()
    )
    require(len(roots) == 3, f"Accept-lock arm must contain 3 cohorts: {arm}")
    return roots


def validate_outer(root: Path, expected_source: str) -> None:
    manifest = load_json(root / "experiment-manifest.json")
    require(manifest.get("status") == "completed",
            "Accept-lock sweep is not completed")
    require(manifest.get("source_commit") == expected_source,
            "Accept-lock sweep source mismatch")
    require(manifest.get("automatic_rerun") is False,
            "Accept-lock sweep automatic-rerun policy mismatch")
    waves = manifest.get("completed_waves", [])
    require(len(waves) == len(ACCEPT_LOCKS_S),
            "Accept-lock sweep wave count mismatch")
    for wave, expected in zip(waves, ACCEPT_LOCKS_S):
        require(float(wave.get("accept_lock_s", -1)) == expected,
                "Accept-lock sweep wave order mismatch")
        results = wave.get("results", [])
        require(len(results) == 3 and all(
            result.get("returncode") == 0 for result in results
        ), f"Accept-lock wave failed: {expected}")


def cell_summary(
    records: dict[tuple[str, int], dict[str, object]],
    baseline: dict[tuple[str, int], dict[str, object]],
    keys: list[tuple[str, int]],
) -> dict[str, object]:
    result = {"run_count": len(keys), "mean": {}, "delta_from_baseline": {}}
    for field in METRIC_FIELDS + EVENT_FIELDS:
        values = [float(records[key][field]) for key in keys]
        deltas = [
            float(records[key][field]) - float(baseline[key][field])
            for key in keys
        ]
        result["mean"][field] = statistics.fmean(values)
        result["delta_from_baseline"][field] = statistics.fmean(deltas)
    speed_deltas = [
        float(records[key]["mean_speed_mps"])
        - float(baseline[key]["mean_speed_mps"])
        for key in keys
    ]
    result["delta_from_baseline"].update({
        "mean_speed_bootstrap_95_ci_mps": bootstrap_mean_ci(speed_deltas),
        "speed_wins": sum(value > 0 for value in speed_deltas),
    })
    return result


def choose_candidate(conditions: dict[str, dict[str, object]]) -> dict[str, object]:
    eligible = []
    scores = {}
    for value in ACCEPT_LOCKS_S:
        label = str(value)
        relative_improvements = []
        condition_results = {}
        qualifies = True
        for condition, result in conditions.items():
            cell = result["cells"][label]
            baseline = result["cells"]["1.0"]
            speed_delta = cell["delta_from_baseline"]["mean_speed_mps"]
            stop_delta = cell["delta_from_baseline"]["stop_time_s"]
            relative = speed_delta / baseline["mean"]["mean_speed_mps"]
            relative_improvements.append(relative)
            condition_results[condition] = {
                "mean_speed_delta_mps": speed_delta,
                "mean_stop_time_delta_s": stop_delta,
                "relative_speed_delta": relative,
            }
            if speed_delta < 0 or stop_delta > 0:
                qualifies = False
        scores[label] = {
            "eligible": qualifies,
            "topology_balanced_relative_speed_delta": statistics.fmean(
                relative_improvements),
            "worst_condition_relative_speed_delta": min(
                relative_improvements),
            "conditions": condition_results,
        }
        if qualifies:
            eligible.append(label)
    selected = None
    if eligible:
        selected = max(
            eligible,
            key=lambda label: (
                scores[label]["worst_condition_relative_speed_delta"],
                scores[label]["topology_balanced_relative_speed_delta"],
            ),
        )
    return {
        "rule": (
            "A new candidate is eligible only when mean speed is not lower "
            "and mean stop time is not higher than the 1.0 s baseline in both "
            "intersection topologies. Among eligible candidates, maximize the "
            "worst-topology relative speed delta, then the balanced mean."
        ),
        "eligible_candidates_s": [float(label) for label in eligible],
        "selected_accept_lock_s": None if selected is None else float(selected),
        "candidate_scores": scores,
    }


def summarize(
    baseline_roots: list[Path], short_lock_roots: list[Path],
    sweep_root: Path, baseline_source: str, short_lock_source: str,
    sweep_source: str,
) -> dict[str, object]:
    validate_outer(sweep_root, sweep_source)
    cells = {
        "1.0": collect(baseline_roots, baseline_source, 1.0, 1.0, 1.0),
        "0.1": collect(short_lock_roots, short_lock_source, 0.1, 0.1, 0.1),
    }
    for value in ACCEPT_LOCKS_S:
        cells[str(value)] = collect(
            sweep_roots(sweep_root, value), sweep_source, 1.0, value, 1.0)
    require(all(len(records) == 15 for records in cells.values()),
            "each Accept-lock cell must contain 15 runs")
    keys = set(cells["1.0"])
    require(all(set(records) == keys for records in cells.values()),
            "Accept-lock cell run keys do not match")
    for key in sorted(keys):
        require(len({
            records[key]["fixed_input_sha256"] for records in cells.values()
        }) == 1, f"fixed input mismatch: {key}")
        require(len({
            records[key]["fixed_input_prefix_sha256"] for records in cells.values()
        }) == 1, f"fixed input prefix mismatch: {key}")

    by_condition = defaultdict(list)
    for key in sorted(keys):
        by_condition[key[0]].append(key)
    conditions = {}
    for condition, selected in sorted(by_condition.items()):
        conditions[condition] = {
            "cells": {
                label: cell_summary(records, cells["1.0"], selected)
                for label, records in cells.items()
            }
        }
    selection = choose_candidate(conditions)
    return {
        "analysis": "intersection-accept-lock-sweep",
        "classification": "diagnostic-development-timing-sweep",
        "sources": {
            "1.0": baseline_source,
            "0.1": short_lock_source,
            "intermediate": sweep_source,
        },
        "validated_run_count": sum(len(records) for records in cells.values()),
        "validated_new_run_count": sum(
            len(cells[str(value)]) for value in ACCEPT_LOCKS_S),
        "physical_collision_count": 0,
        "conditions": conditions,
        "selection": selection,
        "paired_runs": [{
            "condition": key[0],
            "seed": key[1],
            "cells": {
                label: {
                    field: records[key][field]
                    for field in METRIC_FIELDS + EVENT_FIELDS
                }
                for label, records in cells.items()
            },
        } for key in sorted(keys)],
        "limitations": [
            "The timing sweep uses development seeds 13-22.",
            "Candidate selection is exploratory and requires unused-seed validation before a performance claim.",
            "A timing compromise does not separate decision re-evaluation from accepted-path refresh.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", action="append", type=Path,
                        required=True)
    parser.add_argument("--short-lock-root", action="append", type=Path,
                        required=True)
    parser.add_argument("--sweep-root", type=Path, required=True)
    parser.add_argument("--baseline-source", default=BASELINE_SOURCE)
    parser.add_argument("--short-lock-source", required=True)
    parser.add_argument("--sweep-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(
        [path.resolve() for path in args.baseline_root],
        [path.resolve() for path in args.short_lock_root],
        args.sweep_root.resolve(), args.baseline_source,
        args.short_lock_source, args.sweep_source,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "ok": True,
        "validated_run_count": report["validated_run_count"],
        "validated_new_run_count": report["validated_new_run_count"],
        "selected_accept_lock_s": report["selection"]["selected_accept_lock_s"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

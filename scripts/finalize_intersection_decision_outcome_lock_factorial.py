#!/usr/bin/env python3
"""Validate and compare the four outcome-specific decision-lock cells."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

from finalize_intersection_decision_lock_cadence_ablation import (
    BASELINE_SOURCE,
    REQUIRED_ARTIFACTS,
    bootstrap_mean_ci,
    collect,
    load_json,
    require,
)


CELL_SPECS = {
    "accept-long-reject-long": (1.0, 1.0, 1.0),
    "accept-short-reject-short": (0.1, 0.1, 0.1),
    "accept-short-reject-long": (1.0, 0.1, 1.0),
    "accept-long-reject-short": (1.0, 1.0, 0.1),
}
EVENT_FIELDS = (
    "attempts", "evaluated", "unsupported", "started", "decisions",
    "accepts", "rejects", "applied", "waiting_for_agreement",
    "cancellations", "deferred", "duplicate_suppressed",
)
METRIC_FIELDS = ("mean_speed_mps", "stop_time_s", "hard_brake_time_s")


def factorial_arm_roots(factorial_root: Path, arm: str) -> list[Path]:
    arm_root = factorial_root / arm
    require(arm_root.is_dir(), f"factorial arm root missing: {arm_root}")
    roots = sorted(
        path for path in arm_root.iterdir()
        if path.is_dir() and (path / "experiment-manifest.json").is_file()
    )
    require(len(roots) == 3, f"factorial arm must contain 3 cohorts: {arm_root}")
    return roots


def validate_outer_manifest(factorial_root: Path, expected_source: str) -> None:
    manifest = load_json(factorial_root / "experiment-manifest.json")
    require(manifest.get("status") == "completed",
            "factorial outer experiment is not completed")
    require(manifest.get("source_commit") == expected_source,
            "factorial outer source commit mismatch")
    require(manifest.get("automatic_rerun") is False,
            "factorial outer automatic-rerun policy mismatch")
    waves = manifest.get("completed_waves", [])
    require(len(waves) == 2, "factorial outer manifest must contain two waves")
    require(all(
        result.get("returncode") == 0
        for wave in waves for result in wave.get("results", [])
    ), "factorial outer manifest contains a failed cohort")


def cell_summary(records: list[dict[str, object]],
                 baseline: list[dict[str, object]]) -> dict[str, object]:
    require(len(records) == len(baseline), "cell and baseline sizes differ")
    result = {
        "run_count": len(records),
        "mean": {},
        "delta_from_baseline": {},
    }
    for field in METRIC_FIELDS + EVENT_FIELDS:
        values = [float(record[field]) for record in records]
        deltas = [
            float(record[field]) - float(before[field])
            for record, before in zip(records, baseline)
        ]
        result["mean"][field] = statistics.fmean(values)
        result["delta_from_baseline"][field] = statistics.fmean(deltas)
    speed_deltas = [
        float(record["mean_speed_mps"]) - float(before["mean_speed_mps"])
        for record, before in zip(records, baseline)
    ]
    result["delta_from_baseline"].update({
        "mean_speed_bootstrap_95_ci_mps": bootstrap_mean_ci(speed_deltas),
        "speed_wins": sum(value > 0 for value in speed_deltas),
    })
    return result


def paired_effects(cells: dict[str, dict[tuple[str, int], dict[str, object]]],
                   keys: list[tuple[str, int]], field: str) -> dict[str, object]:
    def differences(left: str, right: str) -> list[float]:
        return [
            float(cells[left][key][field]) - float(cells[right][key][field])
            for key in keys
        ]

    accept_when_reject_long = differences(
        "accept-short-reject-long", "accept-long-reject-long")
    accept_when_reject_short = differences(
        "accept-short-reject-short", "accept-long-reject-short")
    reject_when_accept_long = differences(
        "accept-long-reject-short", "accept-long-reject-long")
    reject_when_accept_short = differences(
        "accept-short-reject-short", "accept-short-reject-long")
    interaction = [
        float(cells["accept-short-reject-short"][key][field])
        - float(cells["accept-short-reject-long"][key][field])
        - float(cells["accept-long-reject-short"][key][field])
        + float(cells["accept-long-reject-long"][key][field])
        for key in keys
    ]

    def describe(values: list[float]) -> dict[str, object]:
        result = {"mean": statistics.fmean(values)}
        if field == "mean_speed_mps":
            result["bootstrap_95_ci"] = bootstrap_mean_ci(values)
        return result

    return {
        "shorten_accept_when_reject_long": describe(accept_when_reject_long),
        "shorten_accept_when_reject_short": describe(accept_when_reject_short),
        "shorten_reject_when_accept_long": describe(reject_when_accept_long),
        "shorten_reject_when_accept_short": describe(reject_when_accept_short),
        "interaction": describe(interaction),
    }


def summarize(
    baseline_roots: list[Path], short_lock_roots: list[Path],
    factorial_root: Path, baseline_source: str, short_lock_source: str,
    factorial_source: str,
) -> dict[str, object]:
    validate_outer_manifest(factorial_root, factorial_source)
    cells = {
        "accept-long-reject-long": collect(
            baseline_roots, baseline_source, *CELL_SPECS[
                "accept-long-reject-long"]),
        "accept-short-reject-short": collect(
            short_lock_roots, short_lock_source, *CELL_SPECS[
                "accept-short-reject-short"]),
        "accept-short-reject-long": collect(
            factorial_arm_roots(
                factorial_root, "accept-short-reject-long"),
            factorial_source, *CELL_SPECS["accept-short-reject-long"]),
        "accept-long-reject-short": collect(
            factorial_arm_roots(
                factorial_root, "accept-long-reject-short"),
            factorial_source, *CELL_SPECS["accept-long-reject-short"]),
    }
    for name, records in cells.items():
        require(len(records) == 15, f"{name} must contain exactly 15 runs")
    key_set = set(cells["accept-long-reject-long"])
    require(all(set(records) == key_set for records in cells.values()),
            "factorial cell run keys do not match")
    for key in sorted(key_set):
        hashes = {
            records[key]["fixed_input_sha256"] for records in cells.values()
        }
        prefixes = {
            records[key]["fixed_input_prefix_sha256"]
            for records in cells.values()
        }
        require(len(hashes) == 1, f"fixed input mismatch: {key}")
        require(len(prefixes) == 1, f"fixed input prefix mismatch: {key}")

    condition_keys = defaultdict(list)
    for key in sorted(key_set):
        condition_keys[key[0]].append(key)
    conditions = {}
    for condition, keys in sorted(condition_keys.items()):
        baseline = [cells["accept-long-reject-long"][key] for key in keys]
        summaries = {}
        for name, records in cells.items():
            summaries[name] = cell_summary(
                [records[key] for key in keys], baseline)
        best = max(
            summaries,
            key=lambda name: summaries[name]["mean"]["mean_speed_mps"],
        )
        conditions[condition] = {
            "cells": summaries,
            "best_cell_by_mean_speed": best,
            "factorial_effects": {
                field: paired_effects(cells, keys, field)
                for field in ("mean_speed_mps", "stop_time_s", "accepts",
                              "rejects", "cancellations")
            },
        }

    unsupported = {}
    for name, records in cells.items():
        reasons = Counter()
        for record in records.values():
            reasons.update(record["unsupported_reasons"])
        unsupported[name] = {
            "total": sum(int(record["unsupported"])
                         for record in records.values()),
            "reasons": dict(reasons),
            "reasons_unattributed": sum(
                int(record["unsupported_reasons_unattributed"])
                for record in records.values()),
        }

    paired_runs = []
    for key in sorted(key_set):
        paired_runs.append({
            "condition": key[0],
            "seed": key[1],
            "cells": {
                name: {
                    field: record[key][field]
                    for field in METRIC_FIELDS + EVENT_FIELDS
                }
                for name, record in cells.items()
            },
        })
    return {
        "analysis": "intersection-decision-outcome-lock-factorial",
        "classification": "diagnostic-development-factorial-ablation",
        "sources": {
            "accept-long-reject-long": baseline_source,
            "accept-short-reject-short": short_lock_source,
            "outcome-specific-cells": factorial_source,
        },
        "validated_run_count": sum(len(records) for records in cells.values()),
        "validated_new_run_count": (
            len(cells["accept-short-reject-long"])
            + len(cells["accept-long-reject-short"])),
        "physical_collision_count": 0,
        "prediction_support": unsupported,
        "conditions": conditions,
        "paired_runs": paired_runs,
        "limitations": [
            "The factorial uses development seeds 13-22 and is not an independent holdout.",
            "The lock guard also suppresses alternative-path generation, so Accept-lock effects combine decision reevaluation and path refresh.",
            "Only the two missing factorial cells are new runs; the all-long and all-short cells reuse validated prior batches.",
            "The result diagnoses controller timing and does not by itself validate a final method.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", action="append", type=Path,
                        required=True)
    parser.add_argument("--short-lock-root", action="append", type=Path,
                        required=True)
    parser.add_argument("--factorial-root", type=Path, required=True)
    parser.add_argument("--baseline-source", default=BASELINE_SOURCE)
    parser.add_argument("--short-lock-source", required=True)
    parser.add_argument("--factorial-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(
        [path.resolve() for path in args.baseline_root],
        [path.resolve() for path in args.short_lock_root],
        args.factorial_root.resolve(), args.baseline_source,
        args.short_lock_source, args.factorial_source,
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
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

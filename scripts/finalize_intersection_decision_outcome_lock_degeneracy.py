#!/usr/bin/env python3
"""Finalize the stopped one-wave outcome-lock degeneracy diagnostic."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
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


ARM = "accept-short-reject-long"
OMITTED_ARM = "accept-long-reject-short"
GENERIC_LOCK_S = 1.0
ACCEPT_LOCK_S = 0.1
REJECT_LOCK_S = 1.0
COMPARISON_ARTIFACTS = (
    "evaluation-metrics.json",
    "negotiations.jsonl",
    "vehicle-states.jsonl",
    "conflicts.jsonl",
)
METRIC_FIELDS = ("mean_speed_mps", "stop_time_s", "hard_brake_time_s")
EVENT_FIELDS = (
    "attempts", "evaluated", "unsupported", "started", "decisions",
    "accepts", "rejects", "applied", "waiting_for_agreement",
    "cancellations", "deferred", "duplicate_suppressed",
)


def arm_roots(factorial_root: Path) -> list[Path]:
    root = factorial_root / ARM
    require(root.is_dir(), f"factorial arm root missing: {root}")
    roots = sorted(
        path for path in root.iterdir()
        if path.is_dir() and (path / "experiment-manifest.json").is_file()
    )
    require(len(roots) == 3, f"factorial arm must contain 3 cohorts: {root}")
    return roots


def validate_outer_manifest(factorial_root: Path, expected_source: str) -> dict:
    manifest = load_json(factorial_root / "experiment-manifest.json")
    require(manifest.get("status") == "stopped_after_wave_1",
            "factorial outer experiment was not stopped after wave 1")
    require(manifest.get("source_commit") == expected_source,
            "factorial outer source commit mismatch")
    require(manifest.get("automatic_rerun") is False,
            "factorial outer automatic-rerun policy mismatch")
    waves = manifest.get("completed_waves", [])
    require(len(waves) == 1 and waves[0].get("arm") == ARM,
            "outer manifest must contain exactly the completed first wave")
    results = waves[0].get("results", [])
    require(len(results) == 3 and all(
        result.get("returncode") == 0 for result in results
    ), "first wave contains a failed cohort")
    omitted = manifest.get("omitted_waves", [])
    require(len(omitted) == 1 and omitted[0].get("arm") == OMITTED_ARM,
            "outer manifest must identify the omitted redundant arm")
    require(omitted[0].get("reason") == "reject_lock_key_unreachable",
            "unexpected omitted-arm reason")
    return manifest


def run_paths(roots: list[Path]) -> dict[tuple[str, int], Path]:
    result = {}
    for root in roots:
        experiment = load_json(root / "experiment-manifest.json")
        for task in experiment.get("tasks", []):
            run = root / task["case"] / f"seed-{task['seed']}"
            manifest = load_json(run / "manifest.json")
            flows = manifest["flows_vph"]
            condition = f"{manifest['case']}:" + "-".join(
                str(value) for value in flows)
            key = (condition, int(manifest["seed"]))
            require(key not in result, f"duplicate run path: {key}")
            result[key] = run
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def trace_lock_revisits(path: Path) -> dict[str, int]:
    events = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            require(bool(line.strip()), f"blank negotiation line: {path}:{line_number}")
            record = json.loads(line)
            if record.get("event") in {"decision", "suppressed"}:
                events.append(record)
    result = {
        "normalized_accept_decisions": 0,
        "normalized_reject_decisions": 0,
        "accept_decisions_with_same_key_event_under_1s": 0,
        "reject_decisions_with_same_key_event_under_1s": 0,
    }
    for index, event in enumerate(events):
        if (event.get("event") != "decision" or
                event.get("reason") != "normalized-deceleration-propagation"):
            continue
        label = "accept" if event.get("accept") else "reject"
        result[f"normalized_{label}_decisions"] += 1
        key = (
            event.get("receiver_id"), event.get("sender_id"),
            event.get("desired_path_id"),
        )
        start = float(event["sim_time"])
        for later in events[index + 1:]:
            elapsed = float(later["sim_time"]) - start
            if elapsed >= 1.0 - 1e-9:
                break
            later_key = (
                later.get("receiver_id"), later.get("sender_id"),
                later.get("desired_path_id"),
            )
            if later_key == key:
                result[
                    f"{label}_decisions_with_same_key_event_under_1s"
                ] += 1
                break
    return result


def add_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def paired_summary(
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


def summarize(
    baseline_roots: list[Path], short_lock_roots: list[Path],
    factorial_root: Path, baseline_source: str, short_lock_source: str,
    factorial_source: str,
) -> dict[str, object]:
    outer = validate_outer_manifest(factorial_root, factorial_source)
    observed_roots = arm_roots(factorial_root)
    cells = {
        "accept-long-reject-long": collect(
            baseline_roots, baseline_source, 1.0, 1.0, 1.0),
        "accept-short-reject-short": collect(
            short_lock_roots, short_lock_source, 0.1, 0.1, 0.1),
        "accept-short-reject-long": collect(
            observed_roots, factorial_source, GENERIC_LOCK_S,
            ACCEPT_LOCK_S, REJECT_LOCK_S),
    }
    require(all(len(records) == 15 for records in cells.values()),
            "each observed cell must contain exactly 15 runs")
    keys = set(cells["accept-long-reject-long"])
    require(all(set(records) == keys for records in cells.values()),
            "observed cell run keys do not match")

    short_paths = run_paths(short_lock_roots)
    observed_paths = run_paths(observed_roots)
    artifact_matches = {name: 0 for name in COMPARISON_ARTIFACTS}
    exact_record_matches = 0
    comparable_fields = METRIC_FIELDS + EVENT_FIELDS
    for key in sorted(keys):
        short = cells["accept-short-reject-short"][key]
        observed = cells["accept-short-reject-long"][key]
        require(all(short[field] == observed[field]
                    for field in comparable_fields),
                f"outcome-lock cells differ: {key}")
        exact_record_matches += 1
        for name in COMPARISON_ARTIFACTS:
            require(sha256(short_paths[key] / name) ==
                    sha256(observed_paths[key] / name),
                    f"deterministic artifact differs: {key}: {name}")
            artifact_matches[name] += 1

    revisit_counts = {
        "accept-long-reject-long": {},
        "accept-short-reject-short": {},
    }
    for label, paths in (
        ("accept-long-reject-long", run_paths(baseline_roots)),
        ("accept-short-reject-short", short_paths),
    ):
        for run in paths.values():
            add_counts(
                revisit_counts[label],
                trace_lock_revisits(run / "negotiations.jsonl"),
            )
        require(revisit_counts[label]["normalized_reject_decisions"] > 0,
                f"no normalized Reject decisions in {label}")
        require(revisit_counts[label][
            "reject_decisions_with_same_key_event_under_1s"] == 0,
            f"Reject lock key was reachable in {label}")

    condition_keys = defaultdict(list)
    for key in sorted(keys):
        condition_keys[key[0]].append(key)
    conditions = {}
    for condition, selected in sorted(condition_keys.items()):
        baseline = cells["accept-long-reject-long"]
        conditions[condition] = {
            "cells": {
                name: paired_summary(records, baseline, selected)
                for name, records in cells.items()
            },
            "reject_long_minus_reject_short_at_accept_short": {
                field: statistics.fmean(
                    float(cells["accept-short-reject-long"][key][field])
                    - float(cells["accept-short-reject-short"][key][field])
                    for key in selected
                )
                for field in METRIC_FIELDS + EVENT_FIELDS
            },
        }

    return {
        "analysis": "intersection-decision-outcome-lock-degeneracy",
        "classification": "diagnostic-development-mechanism-ablation",
        "sources": {
            "accept-long-reject-long": baseline_source,
            "accept-short-reject-short": short_lock_source,
            "accept-short-reject-long": factorial_source,
        },
        "validated_run_count": 45,
        "validated_new_run_count": 15,
        "physical_collision_count": 0,
        "outer_stop": {
            "status": outer["status"],
            "omitted_arm": OMITTED_ARM,
            "reason": outer["omitted_waves"][0]["reason"],
        },
        "reject_lock_degeneracy": {
            "supported": True,
            "exact_record_matches": exact_record_matches,
            "deterministic_artifact_matches": artifact_matches,
            "trace_revisit_counts": revisit_counts,
            "interpretation": (
                "Reject marks the desired path as judged, while the lock key "
                "includes that desired path ID. No same-key event can reach "
                "the Reject lock before a new desired path ID bypasses it."
            ),
        },
        "conditions": conditions,
        "limitations": [
            "The observed runs use development seeds 13-22.",
            "The omitted accept-long/reject-short arm was not simulated; it is not counted as an observed cell.",
            "The result identifies a degenerate Reject-lock factor but does not separate Accept re-evaluation from alternative-path refresh.",
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

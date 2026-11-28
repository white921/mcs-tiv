#!/usr/bin/env python3
"""Validate and compare the paired lane-heading fallback ablation."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import random
import statistics


BASELINE_SOURCE = "79b14b4effe40570e6310f0e1962839be8fc2f49"
ABLATION_SOURCE = "90e6f9d39dcf7e881cd82516fb9b396191fd0ee4"
REQUIRED_ARTIFACTS = (
    "evaluation-metrics.json",
    "tiv-audit.json",
    "deceleration-audit.json",
    "physical-collisions.jsonl",
    "prediction-events.jsonl",
    "vehicle-states.jsonl",
    "conflicts.jsonl",
    "negotiations.jsonl",
    "runtime.jsonl",
    "fcd.xml.gz",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def condition_key(manifest: dict) -> str:
    flows = manifest["flows_vph"]
    require(isinstance(flows, list), "intersection flows must be a list")
    return f"{manifest['case']}:" + "-".join(str(value) for value in flows)


def metric_totals(metrics: dict) -> dict[str, float]:
    groups = metrics.get("groups", {})
    samples = sum(float(group.get("samples", 0)) for group in groups.values())
    speed_sum = sum(float(group.get("speed_sum", 0)) for group in groups.values())
    require(samples > 0, "evaluation metrics contain no speed samples")
    return {
        "mean_speed_mps": speed_sum / samples,
        "stop_time_s": sum(
            float(group.get("stop_time_s", 0)) for group in groups.values()),
        "hard_brake_time_s": sum(
            float(group.get("hard_brake_time_s", 0))
            for group in groups.values()),
    }


def validate_run(
    run: Path, expected_source: str, expected_fallback: bool
) -> dict[str, object]:
    manifest = load_json(run / "manifest.json")
    require(manifest.get("exit_code") == 0, f"nonzero exit: {run}")
    require(manifest.get("source_unchanged") is True, f"source changed: {run}")
    git = manifest.get("git", {})
    require(git.get("commit") == expected_source,
            f"source commit mismatch: {run}")
    require(git.get("dirty") is False, f"source was dirty: {run}")
    require(manifest.get("decision_method") ==
            "normalized-deceleration-propagation", f"method mismatch: {run}")
    prediction = manifest.get("deceleration_prediction", {})
    require(math.isclose(float(prediction.get("convex_lambda", -1)), 0.95),
            f"lambda mismatch: {run}")
    fallback = prediction.get("lane_metadata_heading_fallback") or {}
    require(fallback.get("enabled", False) is expected_fallback,
            f"fallback flag mismatch: {run}")
    require(manifest.get("diagnostic_traces_enabled") is True,
            f"diagnostic traces disabled: {run}")
    fixed = manifest.get("fixed_vehicle_input") or {}
    require(bool(fixed.get("sha256")) and bool(fixed.get("prefix_sha256")),
            f"fixed input hashes missing: {run}")
    require(manifest.get("checkpoints_written", 0) >= 5,
            f"checkpoint count too small: {run}")
    for name in REQUIRED_ARTIFACTS:
        require((run / name).is_file(), f"required artifact missing: {run / name}")

    metrics = load_json(run / "evaluation-metrics.json")
    safety = metrics.get("physical_safety", {})
    require(safety.get("physical_collision_free") is True,
            f"physical collision detected: {run}")
    require(safety.get("unique_collision_episodes") == 0,
            f"collision episode detected: {run}")
    require((run / "physical-collisions.jsonl").stat().st_size == 0,
            f"physical collision audit is not empty: {run}")
    totals = metric_totals(metrics)
    require(math.isclose(float(manifest["all_speed_mps"]),
                         totals["mean_speed_mps"], rel_tol=1e-9,
                         abs_tol=1e-9), f"speed metric mismatch: {run}")
    audit = load_json(run / "deceleration-audit.json")
    counts = audit.get("counts", {})
    attempts = int(counts.get("active_attempts", 0))
    evaluated = int(counts.get("active_evaluations", 0))
    unsupported = int(counts.get("active_unsupported", 0))
    require(attempts == evaluated + unsupported,
            f"prediction counter mismatch: {run}")
    return {
        "condition": condition_key(manifest),
        "case": manifest["case"],
        "seed": int(manifest["seed"]),
        "fixed_input_sha256": fixed["sha256"],
        "fixed_input_prefix_sha256": fixed["prefix_sha256"],
        "attempts": attempts,
        "unsupported": unsupported,
        **totals,
    }


def collect(
    roots: list[Path], expected_source: str, expected_fallback: bool
) -> dict[tuple[str, int], dict[str, object]]:
    runs = {}
    declared = 0
    for root in roots:
        experiment = load_json(root / "experiment-manifest.json")
        require(experiment.get("status") == "completed",
                f"experiment is not completed: {root}")
        tasks = experiment.get("tasks", [])
        declared += len(tasks)
        require(experiment.get("completed_simulations") == len(tasks),
                f"completed count mismatch: {root}")
        require(experiment.get("failed_simulations") == 0,
                f"failed simulation present: {root}")
        for task in tasks:
            run = root / task["case"] / f"seed-{task['seed']}"
            record = validate_run(run, expected_source, expected_fallback)
            key = (str(record["condition"]), int(record["seed"]))
            require(key not in runs, f"duplicate run key: {key}")
            runs[key] = record
    require(len(runs) == declared, "validated run count mismatch")
    return runs


def bootstrap_mean_ci(values: list[float], draws: int = 20000) -> list[float]:
    require(bool(values), "cannot bootstrap an empty sample")
    rng = random.Random(20261128)
    means = sorted(statistics.fmean(
        values[rng.randrange(len(values))] for _ in values)
        for _ in range(draws))
    return [means[int(0.025 * (draws - 1))],
            means[int(0.975 * (draws - 1))]]


def summarize(
    baseline_roots: list[Path], ablation_roots: list[Path],
    baseline_source: str, ablation_source: str,
) -> dict[str, object]:
    baseline = collect(baseline_roots, baseline_source, False)
    ablation = collect(ablation_roots, ablation_source, True)
    require(len(baseline) == 15, "baseline must contain exactly 15 runs")
    require(len(ablation) == 15, "ablation must contain exactly 15 runs")
    require(set(baseline) == set(ablation), "paired run keys do not match")

    grouped = defaultdict(list)
    paired_runs = []
    for key in sorted(baseline):
        before, after = baseline[key], ablation[key]
        require(before["fixed_input_sha256"] == after["fixed_input_sha256"],
                f"fixed input mismatch: {key}")
        require(before["fixed_input_prefix_sha256"] ==
                after["fixed_input_prefix_sha256"],
                f"fixed input prefix mismatch: {key}")
        pair = {
            "condition": key[0],
            "seed": key[1],
            "fixed_input_sha256": before["fixed_input_sha256"],
            "baseline_speed_mps": before["mean_speed_mps"],
            "ablation_speed_mps": after["mean_speed_mps"],
            "speed_delta_mps": (
                after["mean_speed_mps"] - before["mean_speed_mps"]),
            "stop_time_delta_s": after["stop_time_s"] - before["stop_time_s"],
            "hard_brake_time_delta_s": (
                after["hard_brake_time_s"] - before["hard_brake_time_s"]),
        }
        grouped[key[0]].append((before, after, pair))
        paired_runs.append(pair)

    conditions = {}
    for condition, triples in sorted(grouped.items()):
        baseline_attempts = sum(item[0]["attempts"] for item in triples)
        baseline_unsupported = sum(item[0]["unsupported"] for item in triples)
        ablation_attempts = sum(item[1]["attempts"] for item in triples)
        ablation_unsupported = sum(item[1]["unsupported"] for item in triples)
        require(baseline_attempts > 0 and ablation_attempts > 0,
                f"prediction attempts missing: {condition}")
        baseline_rate = baseline_unsupported / baseline_attempts
        ablation_rate = ablation_unsupported / ablation_attempts
        relative_reduction = (
            (baseline_rate - ablation_rate) / baseline_rate
            if baseline_rate else None)
        speed_deltas = [item[2]["speed_delta_mps"] for item in triples]
        conditions[condition] = {
            "run_count": len(triples),
            "baseline_attempts": baseline_attempts,
            "baseline_unsupported": baseline_unsupported,
            "baseline_unsupported_rate": baseline_rate,
            "ablation_attempts": ablation_attempts,
            "ablation_unsupported": ablation_unsupported,
            "ablation_unsupported_rate": ablation_rate,
            "unsupported_relative_reduction": relative_reduction,
            "baseline_mean_speed_mps": statistics.fmean(
                item[0]["mean_speed_mps"] for item in triples),
            "ablation_mean_speed_mps": statistics.fmean(
                item[1]["mean_speed_mps"] for item in triples),
            "mean_speed_delta_mps": statistics.fmean(speed_deltas),
            "speed_delta_bootstrap_95_ci_mps": bootstrap_mean_ci(speed_deltas),
            "speed_wins": sum(value > 0 for value in speed_deltas),
            "mean_stop_time_delta_s": statistics.fmean(
                item[2]["stop_time_delta_s"] for item in triples),
            "mean_hard_brake_time_delta_s": statistics.fmean(
                item[2]["hard_brake_time_delta_s"] for item in triples),
        }

    mechanism_gate = all(
        item["unsupported_relative_reduction"] is not None
        and item["unsupported_relative_reduction"] >= 0.80
        for item in conditions.values())
    performance_gate = (
        all(item["mean_speed_delta_mps"] > 0 for item in conditions.values())
        and sum(item["speed_wins"] for item in conditions.values()) >= 10)
    return {
        "analysis": "intersection-lane-heading-fallback-ablation",
        "classification": "diagnostic-development-ablation",
        "baseline_source_commit": baseline_source,
        "ablation_source_commit": ablation_source,
        "validated_baseline_run_count": len(baseline),
        "validated_ablation_run_count": len(ablation),
        "physical_collision_count": 0,
        "conditions": conditions,
        "advancement_gate": {
            "mechanism_supported": mechanism_gate,
            "performance_signal_supported": performance_gate,
            "eligible_for_fresh_seed_validation": (
                mechanism_gate and performance_gate),
            "criteria": {
                "unsupported_relative_reduction_each_condition": 0.80,
                "positive_mean_speed_delta_each_condition": True,
                "minimum_total_speed_wins": 10,
            },
        },
        "paired_runs": paired_runs,
        "limitations": [
            "The ablation uses development seeds 13-22 and is not an independent performance holdout.",
            "Only the lane-metadata heading fallback differs between each paired run.",
            "Fresh-seed validation is eligible only when both pre-specified gates pass.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", action="append", type=Path,
                        required=True)
    parser.add_argument("--ablation-root", action="append", type=Path,
                        required=True)
    parser.add_argument("--baseline-source", default=BASELINE_SOURCE)
    parser.add_argument("--ablation-source", default=ABLATION_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(
        [path.resolve() for path in args.baseline_root],
        [path.resolve() for path in args.ablation_root],
        args.baseline_source, args.ablation_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "eligible_for_fresh_seed_validation": report["advancement_gate"][
            "eligible_for_fresh_seed_validation"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

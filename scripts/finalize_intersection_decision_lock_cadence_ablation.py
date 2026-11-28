#!/usr/bin/env python3
"""Validate and compare the paired intersection decision-lock ablation."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import statistics


BASELINE_SOURCE = "90e6f9d39dcf7e881cd82516fb9b396191fd0ee4"
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


def negotiation_counts(path: Path) -> Counter:
    counts = Counter()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            require(bool(line.strip()), f"blank negotiation line: {path}:{line_number}")
            record = json.loads(line)
            counts[str(record.get("event", "unknown"))] += 1
    return counts


def validate_run(
    run: Path, expected_source: str, expected_lock_s: float,
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
    require(fallback.get("enabled") is True,
            f"heading fallback is not enabled: {run}")
    # Runs produced before the cadence flag was introduced have the documented
    # one-second default but no explicit field in their manifest.
    lock_s = float(prediction.get("decision_lock_s", 1.0))
    require(math.isclose(lock_s, expected_lock_s, abs_tol=1e-12),
            f"decision lock mismatch: {run}")
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
    unsupported_reasons = Counter(
        str(record.get("reason", "unknown"))
        for record in audit.get("records", [])
        if record.get("status") == "unsupported"
    )
    retained_unsupported = sum(unsupported_reasons.values())
    require(retained_unsupported <= unsupported,
            f"unsupported reason count exceeds counter: {run}")
    unsupported_reasons_unattributed = unsupported - retained_unsupported
    events = negotiation_counts(run / "negotiations.jsonl")
    require(events["suppressed"] == int(
        counts.get("active_duplicate_decisions_suppressed", 0)),
        f"decision lock counter mismatch: {run}")
    return {
        "condition": condition_key(manifest),
        "case": manifest["case"],
        "seed": int(manifest["seed"]),
        "fixed_input_sha256": fixed["sha256"],
        "fixed_input_prefix_sha256": fixed["prefix_sha256"],
        "decision_lock_s": lock_s,
        "attempts": attempts,
        "evaluated": evaluated,
        "unsupported": unsupported,
        "unsupported_reasons": dict(unsupported_reasons),
        "unsupported_reasons_unattributed": unsupported_reasons_unattributed,
        "duplicate_suppressed": events["suppressed"],
        "decisions": events["decision"],
        "cancellations": events["cancelled"],
        "waiting_for_agreement": events["waiting_for_agreement"],
        **totals,
    }


def collect(
    roots: list[Path], expected_source: str, expected_lock_s: float,
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
            record = validate_run(run, expected_source, expected_lock_s)
            key = (str(record["condition"]), int(record["seed"]))
            require(key not in runs, f"duplicate run key: {key}")
            runs[key] = record
    require(len(runs) == declared, "validated run count mismatch")
    return runs


def bootstrap_mean_ci(values: list[float], draws: int = 20000) -> list[float]:
    require(bool(values), "cannot bootstrap an empty sample")
    rng = random.Random(20261129)
    means = sorted(statistics.fmean(
        values[rng.randrange(len(values))] for _ in values)
        for _ in range(draws))
    return [means[int(0.025 * (draws - 1))],
            means[int(0.975 * (draws - 1))]]


def summarize(
    baseline_roots: list[Path], short_lock_roots: list[Path],
    baseline_source: str, short_lock_source: str,
) -> dict[str, object]:
    baseline = collect(baseline_roots, baseline_source, 1.0)
    short = collect(short_lock_roots, short_lock_source, 0.1)
    require(len(baseline) == 15, "baseline must contain exactly 15 runs")
    require(len(short) == 15, "short-lock batch must contain exactly 15 runs")
    require(set(baseline) == set(short), "paired run keys do not match")

    grouped = defaultdict(list)
    paired_runs = []
    for key in sorted(baseline):
        before, after = baseline[key], short[key]
        require(before["fixed_input_sha256"] == after["fixed_input_sha256"],
                f"fixed input mismatch: {key}")
        require(before["fixed_input_prefix_sha256"] ==
                after["fixed_input_prefix_sha256"],
                f"fixed input prefix mismatch: {key}")
        pair = {
            "condition": key[0],
            "seed": key[1],
            "baseline_speed_mps": before["mean_speed_mps"],
            "short_lock_speed_mps": after["mean_speed_mps"],
            "speed_delta_mps": after["mean_speed_mps"] - before["mean_speed_mps"],
            "stop_time_delta_s": after["stop_time_s"] - before["stop_time_s"],
            "hard_brake_time_delta_s": (
                after["hard_brake_time_s"] - before["hard_brake_time_s"]),
            "attempt_delta": after["attempts"] - before["attempts"],
            "baseline_unsupported": before["unsupported"],
            "short_lock_unsupported": after["unsupported"],
            "unsupported_delta": after["unsupported"] - before["unsupported"],
            "short_lock_unsupported_reasons": after["unsupported_reasons"],
            "short_lock_unsupported_reasons_unattributed": (
                after["unsupported_reasons_unattributed"]),
            "decision_delta": after["decisions"] - before["decisions"],
            "duplicate_suppressed_delta": (
                after["duplicate_suppressed"] - before["duplicate_suppressed"]),
            "cancellation_delta": (
                after["cancellations"] - before["cancellations"]),
        }
        grouped[key[0]].append(pair)
        paired_runs.append(pair)

    conditions = {}
    for condition, pairs in sorted(grouped.items()):
        speed_deltas = [item["speed_delta_mps"] for item in pairs]
        conditions[condition] = {
            "run_count": len(pairs),
            "mean_speed_delta_mps": statistics.fmean(speed_deltas),
            "speed_delta_bootstrap_95_ci_mps": bootstrap_mean_ci(speed_deltas),
            "speed_wins": sum(value > 0 for value in speed_deltas),
            "mean_stop_time_delta_s": statistics.fmean(
                item["stop_time_delta_s"] for item in pairs),
            "mean_hard_brake_time_delta_s": statistics.fmean(
                item["hard_brake_time_delta_s"] for item in pairs),
            "mean_attempt_delta": statistics.fmean(
                item["attempt_delta"] for item in pairs),
            "baseline_unsupported_total": sum(
                item["baseline_unsupported"] for item in pairs),
            "short_lock_unsupported_total": sum(
                item["short_lock_unsupported"] for item in pairs),
            "short_lock_unsupported_reasons_unattributed": sum(
                item["short_lock_unsupported_reasons_unattributed"]
                for item in pairs),
            "mean_unsupported_delta": statistics.fmean(
                item["unsupported_delta"] for item in pairs),
            "mean_decision_delta": statistics.fmean(
                item["decision_delta"] for item in pairs),
            "mean_duplicate_suppressed_delta": statistics.fmean(
                item["duplicate_suppressed_delta"] for item in pairs),
            "mean_cancellation_delta": statistics.fmean(
                item["cancellation_delta"] for item in pairs),
        }

    pair_lookup = {(item["condition"], item["seed"]): item
                   for item in paired_runs}
    eval5_key = "eval5:300-300-300-300"
    severe_seed_stop_improved = all(
        pair_lookup[(eval5_key, seed)]["stop_time_delta_s"] < 0
        for seed in (15, 20))
    cadence_signal = (
        all(item["mean_speed_delta_mps"] > 0 for item in conditions.values())
        and all(item["mean_stop_time_delta_s"] < 0 for item in conditions.values())
        and severe_seed_stop_improved)
    short_lock_unsupported_reasons = Counter()
    for record in short.values():
        short_lock_unsupported_reasons.update(record["unsupported_reasons"])
    return {
        "analysis": "intersection-decision-lock-cadence-ablation",
        "classification": "diagnostic-development-ablation",
        "baseline_source_commit": baseline_source,
        "short_lock_source_commit": short_lock_source,
        "validated_baseline_run_count": len(baseline),
        "validated_short_lock_run_count": len(short),
        "physical_collision_count": 0,
        "prediction_support": {
            "baseline_unsupported_total": sum(
                int(record["unsupported"]) for record in baseline.values()),
            "short_lock_unsupported_total": sum(
                int(record["unsupported"]) for record in short.values()),
            "short_lock_unsupported_reasons": dict(
                short_lock_unsupported_reasons),
            "baseline_unsupported_reasons_unattributed": sum(
                int(record["unsupported_reasons_unattributed"])
                for record in baseline.values()),
            "short_lock_unsupported_reasons_unattributed": sum(
                int(record["unsupported_reasons_unattributed"])
                for record in short.values()),
        },
        "conditions": conditions,
        "cadence_hypothesis": {
            "supported": cadence_signal,
            "severe_eval5_seed_stop_improved": severe_seed_stop_improved,
            "criteria": {
                "positive_mean_speed_delta_each_condition": True,
                "negative_mean_stop_time_delta_each_condition": True,
                "negative_stop_time_delta_eval5_seeds": [15, 20],
            },
        },
        "paired_runs": paired_runs,
        "limitations": [
            "The ablation uses development seeds 13-22 and is not an independent holdout.",
            "Only the active proposal decision-lock duration differs between each paired run.",
            "Unsupported predictions are retained as a cadence outcome rather than treated as an invalid run.",
            "The result diagnoses controller cadence and does not by itself validate a final method.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", action="append", type=Path,
                        required=True)
    parser.add_argument("--short-lock-root", action="append", type=Path,
                        required=True)
    parser.add_argument("--baseline-source", default=BASELINE_SOURCE)
    parser.add_argument("--short-lock-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(
        [path.resolve() for path in args.baseline_root],
        [path.resolve() for path in args.short_lock_root],
        args.baseline_source, args.short_lock_source,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "ok": True,
        "cadence_hypothesis_supported": report["cadence_hypothesis"]["supported"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

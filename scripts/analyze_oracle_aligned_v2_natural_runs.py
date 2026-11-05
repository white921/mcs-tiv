#!/usr/bin/env python3
"""Audit and compare paired 300-second Yamashita and fixed-v2 runs."""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import statistics
from pathlib import Path


CASES = ("eval3", "eval5", "eval7")
SEEDS = tuple(range(23, 33))
METRICS = (
    "mean_speed_mps", "stop_rate", "hard_brake_rate",
    "vehicles_exited_by_300s", "negotiation_decisions",
    "physical_collision_episodes",
)
FATAL = re.compile(
    r"Traceback \(most recent call last\)|Segmentation fault|"
    r"Unhandled exception|Fatal error", re.IGNORECASE)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1,
                       max(0, math.ceil(probability * len(ordered)) - 1))]


def last_jsonl_record(path: Path) -> dict:
    with path.open("rb") as stream:
        stream.seek(0, 2)
        end = stream.tell()
        if not end:
            raise ValueError(f"empty JSONL file: {path}")
        position = end - 1
        while position >= 0:
            stream.seek(position)
            if stream.read(1) == b"\n" and position < end - 1:
                break
            position -= 1
        stream.seek(position + 1)
        return json.loads(stream.read().decode("utf-8").strip())


def negotiation_decisions(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip() and json.loads(line).get("event") == "decision":
                count += 1
    return count


def run_metrics(run_dir: Path) -> dict:
    manifest = read_json(run_dir / "manifest.json")
    evaluation = read_json(run_dir / "evaluation-metrics.json")
    groups = evaluation.get("groups", {})
    samples = sum(float(group.get("samples", 0)) for group in groups.values())
    stop_time = sum(float(group.get("stop_time_s", 0)) for group in groups.values())
    hard_brake_time = sum(
        float(group.get("hard_brake_time_s", 0)) for group in groups.values())
    final_frame = last_jsonl_record(run_dir / "vehicle-states.jsonl")
    active_generated = sum(
        str(vehicle.get("vehicle_id")) != "stone"
        for vehicle in final_frame.get("vehicles", ()))
    generated = sum(manifest.get("vehicle_mix") or ())
    safety = evaluation.get("physical_safety", {})
    return {
        "mean_speed_mps": float(manifest["all_speed_mps"]),
        "stop_rate": stop_time / (samples * 0.1),
        "hard_brake_rate": hard_brake_time / (samples * 0.1),
        "vehicles_exited_by_300s": generated - active_generated,
        "negotiation_decisions": negotiation_decisions(
            run_dir / "negotiations.jsonl"),
        "physical_collision_episodes": int(
            safety.get("unique_collision_episodes", -1)),
        "physical_collision_free": safety.get("physical_collision_free"),
        "fixed_input_sha256": manifest.get(
            "fixed_vehicle_input", {}).get("sha256"),
        "git_commit": manifest.get("git", {}).get("commit"),
        "exit_code": manifest.get("exit_code"),
        "source_unchanged": manifest.get("source_unchanged"),
    }


def audit_batch(root: Path, method: str, expected_commit: str) -> list[str]:
    errors = []
    batch = read_json(root / "experiment-manifest.json")
    checks = {
        "status": batch.get("status") == "completed",
        "completed": batch.get("completed_simulations") == 30,
        "failed": batch.get("failed_simulations") == 0,
        "duration": float(batch.get("duration_s", -1)) == 300.0,
        "workers": batch.get("workers") == 10,
        "cases": tuple(batch.get("cases", ())) == CASES,
        "seeds": sorted({task["seed"] for task in batch.get("tasks", ())})
        == list(SEEDS),
        "commit": batch.get("git", {}).get("commit") == expected_commit,
        "clean": batch.get("git", {}).get("dirty") is False,
        "method": (
            str(batch.get("method", "")).startswith("yamashita")
            if method == "yamashita"
            else batch.get("method") == "deceleration-propagation"),
    }
    for name, passed in checks.items():
        if not passed:
            errors.append(f"{root}: failed batch check {name}")
    for case in CASES:
        for seed in SEEDS:
            run_dir = root / case / f"seed-{seed}"
            for name in (
                "manifest.json", "evaluation-metrics.json",
                "physical-collisions.jsonl", "negotiations.jsonl",
                "vehicle-states.jsonl", "stdout.log", "stderr.log"):
                if not (run_dir / name).is_file():
                    errors.append(f"missing {run_dir / name}")
            if not (run_dir / "manifest.json").is_file():
                continue
            metrics = run_metrics(run_dir)
            if metrics["exit_code"] != 0 or metrics["source_unchanged"] is not True:
                errors.append(f"invalid run manifest: {run_dir}")
            if metrics["git_commit"] != expected_commit:
                errors.append(f"source commit mismatch: {run_dir}")
            collision_records = sum(
                bool(line.strip()) for line in
                (run_dir / "physical-collisions.jsonl").read_text(
                    encoding="utf-8", errors="replace").splitlines())
            expected_free = metrics["physical_collision_episodes"] == 0
            if metrics["physical_collision_free"] is not expected_free:
                errors.append(f"inconsistent collision summary: {run_dir}")
            if ((collision_records == 0)
                    != (metrics["physical_collision_episodes"] == 0)):
                errors.append(f"inconsistent collision log: {run_dir}")
            for name in ("stdout.log", "stderr.log"):
                text = (run_dir / name).read_text(
                    encoding="utf-8", errors="replace")
                if FATAL.search(text):
                    errors.append(f"fatal log signature: {run_dir / name}")
    return errors


def macro_case_mean(rows: list[dict], field: str) -> float:
    return statistics.fmean(
        statistics.fmean(row[field] for row in rows if row["case"] == case)
        for case in CASES)


def paired_seed_bootstrap(
    rows: list[dict], field: str, repetitions: int, seed: int,
) -> list[float]:
    indexed = {(row["case"], row["seed"]): row[field] for row in rows}
    rng = random.Random(seed)
    draws = []
    for _ in range(repetitions):
        sampled = [rng.choice(SEEDS) for _ in SEEDS]
        draws.append(statistics.fmean(
            statistics.fmean(indexed[(case, selected)] for selected in sampled)
            for case in CASES))
    return sorted(draws)


def comparison(rows: list[dict], metric: str, repetitions: int, seed: int) -> dict:
    difference = f"{metric}_difference"
    draws = paired_seed_bootstrap(rows, difference, repetitions, seed)
    return {
        "baseline_macro_case_mean": macro_case_mean(rows, f"baseline_{metric}"),
        "proposal_macro_case_mean": macro_case_mean(rows, f"proposal_{metric}"),
        "proposal_minus_baseline_macro_case_mean": macro_case_mean(rows, difference),
        "paired_seed_bootstrap_95pct": [
            percentile(draws, 0.025), percentile(draws, 0.975)],
        "by_case": {
            case: statistics.fmean(
                row[difference] for row in rows if row["case"] == case)
            for case in CASES
        },
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render(rows: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    displayed = (
        ("mean_speed_mps", "Mean speed difference (m/s)"),
        ("stop_rate", "Stop-rate difference"),
        ("vehicles_exited_by_300s", "Exited-vehicle difference"),
    )
    fig, axes = plt.subplots(len(displayed), 1, figsize=(10, 10), sharex=True)
    x = range(len(SEEDS))
    for axis, (metric, label) in zip(axes, displayed):
        for case, marker in zip(CASES, ("o", "s", "^")):
            subset = sorted(
                (row for row in rows if row["case"] == case),
                key=lambda row: row["seed"])
            axis.plot(x, [row[f"{metric}_difference"] for row in subset],
                      marker=marker, label=case)
        axis.axhline(0, color="#333", linewidth=0.8)
        axis.set_ylabel(label)
        axis.grid(alpha=0.2)
    axes[0].legend()
    axes[-1].set_xticks(list(x), [str(seed) for seed in SEEDS])
    axes[-1].set_xlabel("Paired seed")
    fig.suptitle("Fixed v2 minus Yamashita: 300-second natural runs")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-repetitions", type=int, default=100_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20261105)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output directory already exists")
    args.output.mkdir(parents=True)
    errors = (
        audit_batch(args.baseline, "yamashita", args.expected_source_commit)
        + audit_batch(args.proposal, "proposal", args.expected_source_commit))
    rows = []
    for case in CASES:
        for seed in SEEDS:
            baseline = run_metrics(args.baseline / case / f"seed-{seed}")
            proposal = run_metrics(args.proposal / case / f"seed-{seed}")
            if baseline["fixed_input_sha256"] != proposal["fixed_input_sha256"]:
                errors.append(f"fixed input mismatch: {case}:seed-{seed}")
            row = {"case": case, "seed": seed}
            for metric in METRICS:
                row[f"baseline_{metric}"] = baseline[metric]
                row[f"proposal_{metric}"] = proposal[metric]
                row[f"{metric}_difference"] = proposal[metric] - baseline[metric]
            rows.append(row)
    audit = {
        "schema": "oracle-aligned-v2-natural-run-audit-v1",
        "status": "passed" if not errors else "failed",
        "runs": len(rows) * 2,
        "physical_collision_episodes": {
            "baseline": sum(
                row["baseline_physical_collision_episodes"] for row in rows),
            "proposal": sum(
                row["proposal_physical_collision_episodes"] for row in rows),
        },
        "errors": errors,
    }
    (args.output / "audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit(f"natural-run audit failed with {len(errors)} errors")
    comparisons = {
        metric: comparison(rows, metric, args.bootstrap_repetitions,
                           args.bootstrap_seed + index)
        for index, metric in enumerate(METRICS)
    }
    summary = {
        "schema": "oracle-aligned-v2-natural-run-analysis-v1",
        "cases": list(CASES), "seeds": list(SEEDS),
        "duration_s": 300, "paired_runs": len(rows),
        "bootstrap": {
            "repetitions": args.bootstrap_repetitions,
            "seed": args.bootstrap_seed,
            "unit": "paired seed resampled jointly across cases",
            "aggregation": "equal-case macro mean",
        },
        "comparisons": comparisons,
        "limitations": [
            "This network-wide 300-second evaluation is separate from the "
            "10-second counterfactual decision-regret holdout.",
            "vehicles_exited_by_300s is generated vehicles minus active "
            "generated vehicles in the final trace frame; physical collision "
            "audits are reported alongside it because collision removals would "
            "confound this throughput proxy.",
        ],
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_csv(args.output / "paired-runs.csv", rows)
    render(rows, args.output / "natural-performance.png")
    (args.output / "experiment-manifest.json").write_text(
        json.dumps({
            "schema": "oracle-aligned-v2-natural-analysis-run-v1",
            "status": "completed", "analysis_only": True,
            "new_simulation": False, "paired_runs": len(rows),
            "baseline_root": str(args.baseline.resolve()),
            "proposal_root": str(args.proposal.resolve()),
            "output_files": ["audit.json", "summary.json", "paired-runs.csv",
                             "natural-performance.png"],
        }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Audit and summarize the completed 600-second fine lambda sweep."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import json
import math
from pathlib import Path
import random
import re
import statistics
import subprocess
import xml.etree.ElementTree as ET


SOURCE_COMMIT = "e0f36fc461a37e179bf831121ef01b982c5121db"
SEEDS = tuple(range(33, 43))
NEW_CANDIDATES = {
    "0525": 0.525,
    "0550": 0.550,
    "0575": 0.575,
    "0625": 0.625,
    "0650": 0.650,
    "0675": 0.675,
}
REUSED_CANDIDATES = (0.50, 0.60, 0.70)
WIDE_SUMMARY_COMMIT = "e4d333df0c88460b0531cf9c94d20536dbed0ae7"
WIDE_SUMMARY_PATH = (
    "results/runs/normalized-convex-lambda000-eval7-r1000-a1000-"
    "seeds33-42-600s-20261117/lambda-wide-sweep-summary.json"
)
FATAL_PATTERN = re.compile(
    r"traceback|segmentation fault|fatal error|connection closed by sumo|"
    r"process exited with code [1-9]|\berror:\s",
    re.IGNORECASE,
)


def root_for(base: Path, tag: str) -> Path:
    worktree = base / f"mcs-tiv-normalized-convex-lambda{tag}-600s-20261119"
    return (
        worktree
        / "results"
        / "runs"
        / f"normalized-convex-lambda{tag}-eval7-r1000-a1000-seeds33-42-600s-20261119"
    )


def summary_value(stderr: str, name: str) -> float:
    match = re.search(rf"^{name}\s*:\s*([0-9.eE+-]+)", stderr, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing {name} in stderr")
    return float(match.group(1))


def open_fcd(path: Path):
    gzip_path = path.with_name(path.name + ".gz")
    if path.is_file():
        return path.open("rb")
    if gzip_path.is_file():
        return gzip.open(gzip_path, "rb")
    parts = sorted(path.parent.glob(path.name + ".gz.part-*"))
    if parts:
        raise RuntimeError(f"split FCD must be reassembled before analysis: {path}")
    raise FileNotFoundError(path)


def fcd_counts(path: Path) -> tuple[int, int, float | None]:
    seen: set[str] = set()
    current: set[str] = set()
    last: set[str] = set()
    last_time = None
    with open_fcd(path) as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag == "vehicle":
                vehicle_id = element.attrib["id"]
                if vehicle_id != "stone":
                    seen.add(vehicle_id)
                    current.add(vehicle_id)
                element.clear()
            elif element.tag == "timestep":
                last = current
                current = set()
                last_time = float(element.attrib["time"])
                element.clear()
    return len(seen), len(last), last_time


def analyze_run(task: tuple[str, float, int, Path]) -> dict[str, object]:
    tag, lambda_value, seed, run = task
    required = (
        "manifest.json",
        "evaluation-metrics.json",
        "tiv-audit.json",
        "deceleration-audit.json",
        "physical-collisions.jsonl",
        "stdout.log",
        "stderr.log",
    )
    missing = [name for name in required if not (run / name).is_file()]
    if missing:
        raise RuntimeError(f"{run}: missing {missing}")
    manifest = json.loads((run / "manifest.json").read_text())
    stderr = (run / "stderr.log").read_text(errors="replace")
    stdout = (run / "stdout.log").read_text(errors="replace")
    evaluation = json.loads((run / "evaluation-metrics.json").read_text())
    tiv = json.loads((run / "tiv-audit.json").read_text())["counts"]
    inserted, residual, last_time = fcd_counts(
        run / "source" / "merge" / "statistics" / "sumoStat.xml"
    )
    scheduled = int(manifest["fixed_vehicle_input"]["prefix_event_count"])
    groups = evaluation["groups"]
    prediction = manifest["deceleration_prediction"]
    return {
        "tag": tag,
        "lambda": lambda_value,
        "seed": seed,
        "all_speed_mps": manifest["all_speed_mps"],
        "requesting_speed_mps": summary_value(stderr, "requesting_speed"),
        "accepting_speed_mps": summary_value(stderr, "accepting_speed"),
        "stop_time_s": sum(groups[group]["stop_time_s"] for group in ("car", "bus")),
        "hard_brake_time_s": sum(
            groups[group]["hard_brake_time_s"] for group in ("car", "bus")
        ),
        "accepted": tiv["accepted"],
        "rejected": tiv["rejected"],
        "scheduled": scheduled,
        "inserted": inserted,
        "uninserted": scheduled - inserted,
        "residual": residual,
        "outflow": inserted - residual,
        "last_fcd_time_s": last_time,
        "collision_episodes": evaluation["physical_safety"]["unique_collision_episodes"],
        "physical_collision_bytes": (run / "physical-collisions.jsonl").stat().st_size,
        "exit_code": manifest["exit_code"],
        "source_unchanged": manifest["source_unchanged"],
        "git_commit": manifest["git"]["commit"],
        "git_dirty": manifest["git"]["dirty"],
        "fixed_input_sha256": manifest["fixed_vehicle_input"]["sha256"],
        "fixed_input_prefix_sha256": manifest["fixed_vehicle_input"]["prefix_sha256"],
        "python_version": manifest["python_version"],
        "sumo_version": manifest["sumo_version"].splitlines()[0],
        "decision_formula": prediction["decision_formula"],
        "convex_lambda": prediction["convex_lambda"],
        "horizon_s": prediction["horizon_s"],
        "maximum_followers": prediction["maximum_followers"],
        "flows_vph": manifest["flows_vph"],
        "input_duration": manifest["input_duration"],
        "bus_share": float(manifest["bus_share"]),
        "bus_allocation": manifest["bus_allocation"],
        "diagnostic_traces_enabled": manifest["diagnostic_traces_enabled"],
        "fatal_log_match": bool(FATAL_PATTERN.search(stderr + "\n" + stdout)),
    }


def aggregate(items: list[dict[str, object]]) -> dict[str, object]:
    def mean(key: str) -> float:
        return statistics.mean(float(item[key]) for item in items)

    accepted = sum(int(item["accepted"]) for item in items)
    rejected = sum(int(item["rejected"]) for item in items)
    worst = min(items, key=lambda item: float(item["all_speed_mps"]))
    best = max(items, key=lambda item: float(item["all_speed_mps"]))
    return {
        "seed_count": len(items),
        "all_speed_mean_mps": mean("all_speed_mps"),
        "all_speed_sample_sd_mps": statistics.stdev(
            float(item["all_speed_mps"]) for item in items
        ),
        "requesting_speed_mean_mps": mean("requesting_speed_mps"),
        "accepting_speed_mean_mps": mean("accepting_speed_mps"),
        "stop_time_mean_s": mean("stop_time_s"),
        "hard_brake_time_mean_s": mean("hard_brake_time_s"),
        "outflow_mean": mean("outflow"),
        "inserted_mean": mean("inserted"),
        "uninserted_mean": mean("uninserted"),
        "residual_mean": mean("residual"),
        "accept_rate": accepted / (accepted + rejected),
        "worst_seed": worst["seed"],
        "worst_seed_all_speed_mps": worst["all_speed_mps"],
        "best_seed": best["seed"],
        "physical_collision_episodes": sum(
            int(item["collision_episodes"]) for item in items
        ),
    }


def load_reused_rows(repo: Path) -> list[dict[str, object]]:
    raw = subprocess.run(
        ["git", "-C", str(repo), "show", f"{WIDE_SUMMARY_COMMIT}:{WIDE_SUMMARY_PATH}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    report = json.loads(raw)
    return [
        row for row in report["per_seed"] if float(row["lambda"]) in REUSED_CANDIDATES
    ]


def bootstrap_against_best(
    grouped: dict[float, list[dict[str, object]]], best_lambda: float
) -> dict[str, object]:
    rng = random.Random(20261120)
    best = grouped[best_lambda]
    output = {}
    for lambda_value, items in grouped.items():
        differences = [
            float(item["all_speed_mps"]) - float(reference["all_speed_mps"])
            for item, reference in zip(items, best, strict=True)
        ]
        samples = sorted(
            sum(differences[rng.randrange(len(differences))] for _ in differences)
            / len(differences)
            for _ in range(200_000)
        )
        output[str(lambda_value)] = {
            "mean_difference_mps": statistics.mean(differences),
            "higher_seed_count": sum(value > 0 for value in differences),
            "percentile_bootstrap_95_ci_mps": [samples[4_999], samples[194_999]],
        }
    return output


def pareto_frontier(aggregates: dict[float, dict[str, object]]) -> list[float]:
    maximize = (
        "all_speed_mean_mps",
        "requesting_speed_mean_mps",
        "accepting_speed_mean_mps",
        "outflow_mean",
    )
    minimize = (
        "stop_time_mean_s",
        "hard_brake_time_mean_s",
        "uninserted_mean",
        "residual_mean",
    )

    def dominates(a: dict[str, object], b: dict[str, object]) -> bool:
        no_worse = all(float(a[key]) >= float(b[key]) for key in maximize)
        no_worse &= all(float(a[key]) <= float(b[key]) for key in minimize)
        better = any(float(a[key]) > float(b[key]) for key in maximize)
        better |= any(float(a[key]) < float(b[key]) for key in minimize)
        return no_worse and better

    return [
        candidate
        for candidate, values in sorted(aggregates.items())
        if not any(
            other != candidate and dominates(other_values, values)
            for other, other_values in aggregates.items()
        )
    ]


def validate_new_rows(
    roots: dict[str, Path], grouped: dict[float, list[dict[str, object]]]
) -> dict[str, object]:
    errors: list[str] = []
    fixed_inputs: dict[int, set[tuple[str, str]]] = {seed: set() for seed in SEEDS}
    expected_formula = "M=(1-lambda)*Z_time+lambda*Z_follow; accept iff M<=0"
    for tag, lambda_value in NEW_CANDIDATES.items():
        root = roots[tag]
        experiment = json.loads((root / "experiment-manifest.json").read_text())
        checks = {
            "status": experiment.get("status") == "completed",
            "completed": experiment.get("completed_simulations") == 10,
            "failed": experiment.get("failed_simulations") == 0,
            "missing": experiment.get("missing_simulations") == 0,
            "source_commit": experiment.get("git", {}).get("commit") == SOURCE_COMMIT,
            "git_clean": experiment.get("git", {}).get("dirty") is False,
            "candidate": math.isclose(
                float(experiment.get("deceleration_convex_lambda", -1)), lambda_value
            ),
            "machine_slots": experiment.get("max_machine_sumo_processes") == 15,
            "slot_violation": experiment.get("machine_slot_violation") is None,
        }
        errors.extend(
            f"lambda {lambda_value}: experiment {name} failed"
            for name, passed in checks.items()
            if not passed
        )
        for item in grouped[lambda_value]:
            seed = int(item["seed"])
            fixed_inputs[seed].add(
                (str(item["fixed_input_sha256"]), str(item["fixed_input_prefix_sha256"]))
            )
            run_checks = {
                "exit_code": item["exit_code"] == 0,
                "source_unchanged": item["source_unchanged"] is True,
                "source_commit": item["git_commit"] == SOURCE_COMMIT,
                "git_clean": item["git_dirty"] is False,
                "fcd_end": math.isclose(
                    float(item["last_fcd_time_s"]), 599.9, abs_tol=0.011
                ),
                "collision_free": item["collision_episodes"] == 0,
                "collision_log_empty": item["physical_collision_bytes"] == 0,
                "python": str(item["python_version"]).startswith("3.15.1"),
                "sumo": item["sumo_version"] == "Eclipse SUMO sumo 1.28.0",
                "formula": item["decision_formula"] == expected_formula,
                "lambda": math.isclose(float(item["convex_lambda"]), lambda_value),
                "horizon": item["horizon_s"] == 10.0,
                "followers": item["maximum_followers"] == 40,
                "flows": item["flows_vph"] == {"requesting": 1000, "accepting": 1000},
                "duration": item["input_duration"] == 600.0,
                "bus_share": item["bus_share"] == 0.25,
                "bus_fixed": item["bus_allocation"] == "fixed",
                "traces_off": item["diagnostic_traces_enabled"] is False,
                "fatal_logs": item["fatal_log_match"] is False,
            }
            errors.extend(
                f"lambda {lambda_value} seed {seed}: {name} failed"
                for name, passed in run_checks.items()
                if not passed
            )
    fixed_match = all(len(values) == 1 for values in fixed_inputs.values())
    if not fixed_match:
        errors.append("fixed inputs differ across new candidates")
    return {
        "ok": not errors,
        "run_count": sum(len(grouped[value]) for value in NEW_CANDIDATES.values()),
        "errors": errors,
        "fixed_inputs_match_across_new_candidates": fixed_match,
    }


def audit_orchestration(path: Path) -> dict[str, object]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    started = [row for row in rows if row.get("event") == "simulation_started"]
    filled = [row for row in rows if row.get("event") == "slot_filled"]
    finished = [row for row in rows if row.get("event") == "simulation_finished"]
    final = [row for row in rows if row.get("event") == "orchestration_finished"]
    expected = list(range(60))
    errors = []
    if [row.get("queue_index") for row in started] != expected:
        errors.append("simulation_started queue order is not 0..59")
    if [row.get("queue_index") for row in filled] != expected:
        errors.append("slot_filled queue order is not 0..59")
    if sorted(row.get("queue_index") for row in finished) != expected:
        errors.append("simulation_finished queue indexes are incomplete or duplicated")
    if any(
        row.get("exit_code") != 0 or row.get("source_unchanged") is not True
        for row in finished
    ):
        errors.append("a finished simulation failed or changed source")
    if len(final) != 1:
        errors.append("orchestration_finished event count is not one")
        final_event = {}
    else:
        final_event = final[0]
        checks = {
            "submitted": final_event.get("submitted_tasks") == 60,
            "total": final_event.get("total_tasks") == 60,
            "max_slots": final_event.get("max_machine_sumo_processes") == 15,
            "slot_violation": final_event.get("machine_slot_violation") is None,
            "not_aborted": final_event.get("aborted") is False,
        }
        errors.extend(
            f"orchestration final {name} failed"
            for name, passed in checks.items()
            if not passed
        )
    return {
        "ok": not errors,
        "errors": errors,
        "started_count": len(started),
        "finished_count": len(finished),
        "final_event": final_event,
    }


def finalize_compression_audits(roots: dict[str, Path]) -> None:
    summary_path = roots["0525"] / "lambda-fine-sweep-summary.json"
    report = json.loads(summary_path.read_text())
    if not report["new_run_audit"]["ok"] or not report["orchestration_audit"]["ok"]:
        raise RuntimeError("pre-compression audit did not pass")
    for tag, lambda_value in NEW_CANDIDATES.items():
        root = roots[tag]
        compression = json.loads((root / "compression-audit.json").read_text())
        split = json.loads((root / "storage-split-audit.json").read_text())
        errors = []
        if compression.get("item_count") != 20 or not compression.get("all_verified"):
            errors.append("compression audit failed")
        if not split.get("all_verified"):
            errors.append("storage split audit failed")
        audit = {
            "audit": "normalized-convex-lambda-fine-sweep-600s-post-run",
            "candidate": lambda_value,
            "tag": tag,
            "ok": not errors,
            "run_count": 10,
            "errors": errors,
            "source_commit": SOURCE_COMMIT,
            "pre_compression_audit_verified": True,
            "orchestration_audit_verified": True,
            "compression_audit_verified": compression.get("all_verified"),
            "storage_split_audit_verified": split.get("all_verified"),
            "diagnostic_traces_expected": False,
            "checkpoints_expected": False,
        }
        (root / "post-run-audit.json").write_text(
            json.dumps(audit, indent=2) + "\n", encoding="utf-8"
        )
        if errors:
            raise RuntimeError(f"lambda {lambda_value}: {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--finalize-compression-audits", action="store_true")
    args = parser.parse_args()
    roots = {tag: root_for(args.base, tag) for tag in NEW_CANDIDATES}
    if args.finalize_compression_audits:
        finalize_compression_audits(roots)
        print("all post-run compression audits passed")
        return
    tasks = [
        (tag, lambda_value, seed, roots[tag] / "eval7" / f"seed-{seed}")
        for tag, lambda_value in NEW_CANDIDATES.items()
        for seed in SEEDS
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        new_rows = list(executor.map(analyze_run, tasks))
    rows = new_rows + load_reused_rows(args.repo)
    rows.sort(key=lambda item: (float(item["lambda"]), int(item["seed"])))
    candidates = sorted({float(item["lambda"]) for item in rows})
    grouped = {
        value: [item for item in rows if float(item["lambda"]) == value]
        for value in candidates
    }
    aggregates = {value: aggregate(items) for value, items in grouped.items()}
    best = max(candidates, key=lambda value: float(aggregates[value]["all_speed_mean_mps"]))
    audit = validate_new_rows(roots, grouped)
    orchestration_audit = audit_orchestration(roots["0525"] / "orchestration.jsonl")
    report = {
        "schema_version": 1,
        "experiment": "normalized-convex-lambda-fine-sweep-600s-20261119",
        "conditions": {
            "case": "eval7",
            "requesting_vph": 1000,
            "accepting_vph": 1000,
            "duration_s": 600,
            "bus_share": 0.25,
            "seeds": list(SEEDS),
            "source_commit": SOURCE_COMMIT,
        },
        "new_candidates": list(NEW_CANDIDATES.values()),
        "reused_candidates": list(REUSED_CANDIDATES),
        "best_lambda_by_all_speed": best,
        "aggregates": {str(value): aggregates[value] for value in candidates},
        "bootstrap_against_best": bootstrap_against_best(grouped, best),
        "pareto_frontier": pareto_frontier(aggregates),
        "new_run_audit": audit,
        "orchestration_audit": orchestration_audit,
        "per_seed": rows,
    }
    output = roots["0525"] / "lambda-fine-sweep-summary.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output)
    print(json.dumps({
        "audit": audit,
        "orchestration_audit": orchestration_audit,
        "best_lambda": best,
        "pareto_frontier": report["pareto_frontier"],
        "aggregates": report["aggregates"],
        "bootstrap_against_best": report["bootstrap_against_best"],
    }, indent=2))
    if not audit["ok"] or not orchestration_audit["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

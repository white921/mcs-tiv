#!/usr/bin/env python3
"""Audit and summarize the lambda=0.525 traffic-flow sweep."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import xml.etree.ElementTree as ET


SOURCE_COMMIT = "255cb645eae0810bc4b8aa1c76f379910fbbf34b"
LAMBDA = 0.525
FORMULA = "M=(1-lambda)*Z_time+lambda*Z_follow; accept iff M<=0"
SPECS = {
    300: tuple(range(33, 43)),
    500: tuple(range(43, 48)),
    700: tuple(range(33, 43)),
    1200: tuple(range(33, 43)),
}
FATAL_PATTERN = re.compile(
    r"traceback|segmentation fault|fatal error|connection closed by sumo|"
    r"process exited with code [1-9]|\berror:\s",
    re.IGNORECASE,
)


def root_for(base: Path, flow: int) -> Path:
    worktree = base / f"mcs-tiv-normalized-convex-lambda0525-r{flow}-600s-20261121"
    return worktree / "results" / "runs" / (
        f"normalized-convex-lambda0525-eval7-r{flow}-a1000-"
        f"seeds{SPECS[flow][0]}-{SPECS[flow][-1]}-600s-20261121"
    )


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
    return hasher.hexdigest()


def summary_value(stderr: str, name: str) -> float:
    match = re.search(rf"^{name}\s*:\s*([0-9.eE+-]+)", stderr, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing {name} in stderr")
    return float(match.group(1))


def fcd_counts(path: Path) -> tuple[int, int, float | None]:
    seen: set[str] = set()
    current: set[str] = set()
    last: set[str] = set()
    last_time = None
    with gzip.open(path, "rb") as stream:
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


def last_runtime_time(path: Path) -> float:
    last = None
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                last = json.loads(line)
    if last is None:
        raise RuntimeError(f"empty runtime log: {path}")
    for key in ("simulation_time_s", "simulation_time", "sim_time_s", "sim_time", "time_s"):
        if key in last:
            return float(last[key])
    raise RuntimeError(f"runtime record lacks simulation time: {path}")


def analyze_run(task: tuple[int, int, Path, Path]) -> dict[str, object]:
    flow, seed, run, worktree = task
    required = (
        "manifest.json", "evaluation-metrics.json", "tiv-audit.json",
        "deceleration-audit.json", "physical-collisions.jsonl", "stdout.log",
        "stderr.log", "runtime.jsonl", "fcd.xml.gz", "negotiations.jsonl",
        "conflicts.jsonl", "vehicle-states.jsonl", "prediction-events.jsonl",
    )
    missing = [name for name in required if not (run / name).is_file()]
    if missing:
        raise RuntimeError(f"{run}: missing {missing}")
    manifest = json.loads((run / "manifest.json").read_text())
    evaluation = json.loads((run / "evaluation-metrics.json").read_text())
    tiv = json.loads((run / "tiv-audit.json").read_text())["counts"]
    stderr = (run / "stderr.log").read_text(errors="replace")
    stdout = (run / "stdout.log").read_text(errors="replace")
    inserted, residual, fcd_end = fcd_counts(run / "fcd.xml.gz")
    checkpoints = sorted((run / "checkpoints").glob("t*/checkpoint.json"))
    checkpoint_errors: list[str] = []
    checkpoint_times = []
    for checkpoint_path in checkpoints:
        checkpoint = json.loads(checkpoint_path.read_text())
        checkpoint_times.append(float(checkpoint.get("simulation_time_s", -1)))
        if checkpoint.get("seed") != seed:
            checkpoint_errors.append(f"{checkpoint_path.name}: seed")
        directory = checkpoint_path.parent
        for name in (checkpoint.get("mcs_state"), checkpoint.get("sumo_state")):
            if not name or not (directory / str(name)).is_file() or (directory / str(name)).stat().st_size == 0:
                checkpoint_errors.append(f"{directory.name}: {name} missing/empty")
    fixed = manifest["fixed_vehicle_input"]
    fixed_path = worktree / str(fixed["path"])
    groups = evaluation["groups"]
    prediction = manifest["deceleration_prediction"]
    scheduled = int(fixed["prefix_event_count"])
    checks = {
        "exit_code": manifest.get("exit_code") == 0,
        "source_unchanged": manifest.get("source_unchanged") is True,
        "source_commit": manifest.get("git", {}).get("commit") == SOURCE_COMMIT,
        "git_clean": manifest.get("git", {}).get("dirty") is False,
        "fixed_input_exists": fixed_path.is_file(),
        "fixed_input_sha256": fixed_path.is_file() and sha256(fixed_path) == fixed.get("sha256"),
        "python": str(manifest.get("python_version", "")).startswith("3.15.1"),
        "sumo": str(manifest.get("sumo_version", "")).splitlines()[0] == "Eclipse SUMO sumo 1.28.0",
        "formula": prediction.get("decision_formula") == FORMULA,
        "lambda": math.isclose(float(prediction.get("convex_lambda", -1)), LAMBDA),
        "horizon": prediction.get("horizon_s") == 10.0,
        "followers": prediction.get("maximum_followers") == 40,
        "flows": manifest.get("flows_vph") == {"requesting": flow, "accepting": 1000},
        "duration": manifest.get("input_duration") == 600.0,
        "bus_share": float(manifest.get("bus_share", -1)) == 0.25,
        "bus_fixed": manifest.get("bus_allocation") == "fixed",
        "diagnostic_traces": manifest.get("diagnostic_traces_enabled") is True,
        "checkpoints": len(checkpoints) == 10 and checkpoint_times == [float(value) for value in range(60, 601, 60)] and not checkpoint_errors,
        "fcd_end": fcd_end is not None and math.isclose(fcd_end, 599.9, abs_tol=0.011),
        "runtime_end": math.isclose(last_runtime_time(run / "runtime.jsonl"), 600.0, abs_tol=0.011),
        "collision_free": evaluation["physical_safety"]["unique_collision_episodes"] == 0,
        "collision_log_empty": (run / "physical-collisions.jsonl").stat().st_size == 0,
        "fatal_logs": FATAL_PATTERN.search(stderr + "\n" + stdout) is None,
    }
    return {
        "flow_requesting_vph": flow,
        "flow_accepting_vph": 1000,
        "seed": seed,
        "all_speed_mps": manifest["all_speed_mps"],
        "requesting_speed_mps": summary_value(stderr, "requesting_speed"),
        "accepting_speed_mps": summary_value(stderr, "accepting_speed"),
        "stop_time_s": sum(groups[group]["stop_time_s"] for group in ("car", "bus")),
        "hard_brake_time_s": sum(groups[group]["hard_brake_time_s"] for group in ("car", "bus")),
        "accepted": tiv["accepted"],
        "rejected": tiv["rejected"],
        "scheduled": scheduled,
        "inserted": inserted,
        "uninserted": scheduled - inserted,
        "residual": residual,
        "outflow": inserted - residual,
        "fcd_end_time_s": fcd_end,
        "collision_episodes": evaluation["physical_safety"]["unique_collision_episodes"],
        "fixed_input_sha256": fixed["sha256"],
        "checks": checks,
        "errors": [name for name, passed in checks.items() if not passed] + checkpoint_errors,
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
        "all_speed_sample_sd_mps": statistics.stdev(float(item["all_speed_mps"]) for item in items),
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
        "best_seed_all_speed_mps": best["all_speed_mps"],
        "physical_collision_episodes": sum(int(item["collision_episodes"]) for item in items),
    }


def validate_experiment(root: Path, flow: int, run_count: int) -> list[str]:
    experiment = json.loads((root / "experiment-manifest.json").read_text())
    checks = {
        "status": experiment.get("status") == "completed",
        "completed": experiment.get("completed_simulations") == run_count,
        "failed": experiment.get("failed_simulations") == 0,
        "source_commit": experiment.get("git", {}).get("commit") == SOURCE_COMMIT,
        "git_clean": experiment.get("git", {}).get("dirty") is False,
        "lambda": math.isclose(float(experiment.get("deceleration_convex_lambda", -1)), LAMBDA),
        "flows": experiment.get("eval7_flows_vph") == {"requesting": flow, "accepting": 1000},
        "duration": experiment.get("duration_s") == 600.0,
        "diagnostic_traces": experiment.get("diagnostic_traces") is True,
        "checkpoint_interval": experiment.get("checkpoint_interval_s") == 60.0,
    }
    return [name for name, passed in checks.items() if not passed]


def finalize_compression(roots: dict[int, Path]) -> None:
    for flow, root in roots.items():
        existing = json.loads((root / "post-run-audit.json").read_text())
        compression = json.loads((root / "compression-audit.json").read_text())
        split = json.loads((root / "storage-split-audit.json").read_text())
        expected = len(SPECS[flow]) * 13
        errors = list(existing.get("errors", []))
        if compression.get("item_count") != expected or not compression.get("all_verified"):
            errors.append("compression audit failed")
        if not split.get("all_verified"):
            errors.append("storage split audit failed")
        existing.update({
            "ok": not errors,
            "errors": errors,
            "compression_audit_verified": compression.get("all_verified") is True,
            "storage_split_audit_verified": split.get("all_verified") is True,
            "compressed_item_count": compression.get("item_count"),
        })
        (root / "post-run-audit.json").write_text(json.dumps(existing, indent=2) + "\n")
        if errors:
            raise RuntimeError(f"flow {flow}: {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--finalize-compression-audits", action="store_true")
    args = parser.parse_args()
    roots = {flow: root_for(args.base, flow) for flow in SPECS}
    if args.finalize_compression_audits:
        finalize_compression(roots)
        print("all post-run compression audits passed")
        return
    tasks = [
        (flow, seed, roots[flow] / "eval7" / f"seed-{seed}", roots[flow].parents[2])
        for flow, seeds in SPECS.items() for seed in seeds
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        rows = list(executor.map(analyze_run, tasks))
    rows.sort(key=lambda item: (int(item["flow_requesting_vph"]), int(item["seed"])))
    grouped = {flow: [item for item in rows if item["flow_requesting_vph"] == flow] for flow in SPECS}
    aggregates = {str(flow): aggregate(items) for flow, items in grouped.items()}
    errors = []
    for flow, items in grouped.items():
        errors.extend(f"flow {flow} seed {item['seed']}: {error}" for item in items for error in item["errors"])
        errors.extend(f"flow {flow} experiment: {error}" for error in validate_experiment(roots[flow], flow, len(items)))
        audit = {
            "schema_version": 1,
            "audit": "normalized-convex-lambda0525-flow-sweep-600s-post-run",
            "flow_requesting_vph": flow,
            "flow_accepting_vph": 1000,
            "source_commit": SOURCE_COMMIT,
            "run_count": len(items),
            "ok": not any(message.startswith(f"flow {flow} ") for message in errors),
            "errors": [message for message in errors if message.startswith(f"flow {flow} ")],
            "pre_compression_audit_verified": True,
            "diagnostic_traces_expected": True,
            "checkpoints_expected_per_run": 10,
        }
        (roots[flow] / "post-run-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    report = {
        "schema_version": 1,
        "experiment": "normalized-convex-lambda0525-flow-sweep-600s-20261121",
        "conditions": {
            "case": "eval7", "lambda": LAMBDA, "accepting_vph": 1000,
            "requesting_vph": list(SPECS), "duration_s": 600, "bus_share": 0.25,
            "source_commit": SOURCE_COMMIT,
        },
        "ok": not errors,
        "errors": errors,
        "aggregates": aggregates,
        "per_seed": rows,
    }
    output = roots[300] / "lambda0525-flow-sweep-summary.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(output)
    print(json.dumps({"ok": not errors, "errors": errors, "aggregates": aggregates}, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

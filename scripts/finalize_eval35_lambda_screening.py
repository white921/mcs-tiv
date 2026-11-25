#!/usr/bin/env python3
"""Audit, compact, and summarize one completed lambda cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import statistics
import xml.etree.ElementTree as ET


SEEDS_BY_CASE = {
    "eval3": tuple(range(13, 23)),
    "eval5": tuple(range(13, 23)),
    "eval7": tuple(range(33, 43)),
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
            size += len(block)
    return hasher.hexdigest(), size


def summary_value(stderr: str, name: str) -> float | None:
    match = re.search(rf"^{re.escape(name)}\s*:\s*([0-9.eE+-]+)", stderr, re.MULTILINE)
    return float(match.group(1)) if match else None


def insertion_counts(path: Path) -> tuple[int, int, float | None]:
    seen: set[str] = set()
    current: set[str] = set()
    last: set[str] = set()
    last_time = None
    for _, element in ET.iterparse(path, events=("end",)):
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


def analyze_run(
    run: Path, *, seed: int, source_commit: str, lambda_value: float
) -> tuple[dict[str, object], list[str]]:
    manifest = read_json(run / "manifest.json")
    metrics = read_json(run / "evaluation-metrics.json")
    deceleration = read_json(run / "deceleration-audit.json")
    tiv = read_json(run / "tiv-audit.json")
    stderr = (run / "stderr.log").read_text(encoding="utf-8", errors="replace")
    statistics_paths = list(run.glob("source/*/statistics/sumoStat.xml"))
    errors: list[str] = []
    if len(statistics_paths) != 1:
        errors.append(f"expected one SUMO statistics XML, found {len(statistics_paths)}")
        inserted = residual = 0
        last_time = None
    else:
        inserted, residual, last_time = insertion_counts(statistics_paths[0])

    groups = metrics.get("groups", {})
    scheduled = int(manifest["fixed_vehicle_input"]["prefix_event_count"])
    collision_episodes = int(
        metrics.get("physical_safety", {}).get("unique_collision_episodes", -1)
    )
    checks = {
        "exit_code": manifest.get("exit_code") == 0,
        "source_unchanged": manifest.get("source_unchanged") is True,
        "source_commit": manifest.get("git", {}).get("commit") == source_commit,
        "git_clean": manifest.get("git", {}).get("dirty") is False,
        "lambda": math.isclose(
            float(manifest.get("deceleration_prediction", {}).get("convex_lambda", -1)),
            lambda_value,
            abs_tol=1e-12,
        ),
        "duration": math.isclose(
            float(metrics.get("physical_safety", {}).get("last_observed_time_s", -1)),
            600.0,
            abs_tol=0.011,
        ),
        "statistics_end": last_time is not None and math.isclose(last_time, 599.9, abs_tol=0.011),
        "collision_free": collision_episodes == 0,
        "python": str(manifest.get("python_version", "")).startswith("3.15.1"),
        "sumo": "1.28.0" in str(manifest.get("sumo_version", "")).splitlines()[0],
    }
    errors.extend(name for name, passed in checks.items() if not passed)

    return {
        "seed": seed,
        "all_speed_mps": float(manifest["all_speed_mps"]),
        "car_speed_mps": float(groups["car"]["mean_speed_mps"]),
        "bus_speed_mps": float(groups["bus"]["mean_speed_mps"]),
        "stop_time_s": sum(float(groups[name]["stop_time_s"]) for name in ("car", "bus")),
        "hard_brake_time_s": sum(
            float(groups[name]["hard_brake_time_s"]) for name in ("car", "bus")
        ),
        "scheduled": scheduled,
        "inserted": inserted,
        "uninserted": scheduled - inserted,
        "residual": residual,
        "outflow": inserted - residual,
        "last_statistics_time_s": last_time,
        "collision_episodes": collision_episodes,
        "proposal_counts": deceleration.get("counts", {}),
        "tiv_counts": tiv.get("counts", {}),
        "stderr_metrics": {
            name: summary_value(stderr, name)
            for name in (
                "all_speed", "car_speed", "bus_speed", "requesting_speed", "accepting_speed"
            )
            if summary_value(stderr, name) is not None
        },
        "fixed_input": manifest["fixed_vehicle_input"],
        "source_sha256": manifest.get("source_sha256", {}),
        "checks": checks,
    }, errors


def aggregate(rows: list[dict[str, object]]) -> dict[str, object]:
    def mean(key: str) -> float:
        return statistics.mean(float(row[key]) for row in rows)

    speeds = [float(row["all_speed_mps"]) for row in rows]
    accepted = sum(int(row["proposal_counts"].get("proposal_accept", 0)) for row in rows)
    rejected = sum(int(row["proposal_counts"].get("proposal_reject", 0)) for row in rows)
    worst = min(rows, key=lambda row: float(row["all_speed_mps"]))
    best = max(rows, key=lambda row: float(row["all_speed_mps"]))
    return {
        "seed_count": len(rows),
        "all_speed_mean_mps": mean("all_speed_mps"),
        "all_speed_sample_sd_mps": statistics.stdev(speeds),
        "car_speed_mean_mps": mean("car_speed_mps"),
        "bus_speed_mean_mps": mean("bus_speed_mps"),
        "stop_time_mean_s": mean("stop_time_s"),
        "hard_brake_time_mean_s": mean("hard_brake_time_s"),
        "outflow_mean": mean("outflow"),
        "inserted_mean": mean("inserted"),
        "uninserted_mean": mean("uninserted"),
        "residual_mean": mean("residual"),
        "proposal_accept_rate": accepted / (accepted + rejected) if accepted + rejected else None,
        "worst_seed": int(worst["seed"]),
        "worst_seed_all_speed_mps": float(worst["all_speed_mps"]),
        "best_seed": int(best["seed"]),
        "physical_collision_episodes": sum(int(row["collision_episodes"]) for row in rows),
    }


def compact_run(run: Path, row: dict[str, object]) -> dict[str, object]:
    raw_paths = [
        run / "prediction-events.jsonl",
        run / "deceleration-audit.json",
        run / "tiv-audit.json",
    ]
    inventory = []
    for path in raw_paths:
        sha256, size = digest(path)
        inventory.append(
            {"path": str(path.relative_to(run)), "sha256": sha256, "size_bytes": size}
        )
    source = run / "source"
    source_file_count = sum(1 for path in source.rglob("*") if path.is_file())
    source_size = sum(path.stat().st_size for path in source.rglob("*") if path.is_file())

    write_json(run / "screening-run-summary.json", row)
    for path in raw_paths:
        path.unlink()
    shutil.rmtree(source)
    audit = {
        "schema_version": 1,
        "ok": True,
        "classification": "diagnostic-development-screening",
        "retained_summary": "screening-run-summary.json",
        "deleted_raw_artifacts": inventory,
        "deleted_reconstructable_source_snapshot": {
            "path": "source",
            "file_count": source_file_count,
            "size_bytes": source_size,
            "source_sha256_recorded_in_manifest": True,
        },
    }
    write_json(run / "retention-audit.json", audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--case", choices=SEEDS_BY_CASE, required=True)
    parser.add_argument("--lambda-value", type=float, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    experiment = read_json(output / "experiment-manifest.json")
    seeds = SEEDS_BY_CASE[args.case]
    errors = []
    if experiment.get("status") != "completed":
        errors.append("experiment_status")
    if experiment.get("completed_simulations") != len(seeds):
        errors.append("completed_simulations")
    if experiment.get("failed_simulations") != 0:
        errors.append("failed_simulations")
    if experiment.get("tasks") != [{"case": args.case, "seed": seed} for seed in seeds]:
        errors.append("tasks")

    rows = []
    for seed in seeds:
        run = output / args.case / f"seed-{seed}"
        row, run_errors = analyze_run(
            run, seed=seed, source_commit=args.source_commit, lambda_value=args.lambda_value
        )
        rows.append(row)
        errors.extend(f"seed-{seed}:{error}" for error in run_errors)
    if errors:
        write_json(output / "post-run-audit.json", {"ok": False, "errors": errors})
        raise RuntimeError("screening audit failed: " + ", ".join(errors[:10]))

    summary = {
        "schema_version": 1,
        "classification": "development-screening",
        "condition": args.condition,
        "case": args.case,
        "lambda": args.lambda_value,
        "source_commit": args.source_commit,
        "seeds": list(seeds),
        "aggregate": aggregate(rows),
        "per_seed": rows,
    }
    write_json(output / "lambda-screening-summary.json", summary)
    retention = [compact_run(output / args.case / f"seed-{seed}", row) for seed, row in zip(seeds, rows)]
    write_json(
        output / "post-run-audit.json",
        {
            "schema_version": 1,
            "ok": True,
            "classification": "development-screening",
            "condition": args.condition,
            "lambda": args.lambda_value,
            "source_commit": args.source_commit,
            "run_count": len(rows),
            "physical_collision_episodes": summary["aggregate"]["physical_collision_episodes"],
            "raw_retention_audits_ok": all(item["ok"] for item in retention),
            "errors": [],
        },
    )
    print(json.dumps({"status": "completed", "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

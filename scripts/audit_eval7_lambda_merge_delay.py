#!/usr/bin/env python3
"""Gate the Eval.7 lambda merge-delay diagnostic before the next batch."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET


LAMBDAS = (0.525, 0.95)
SEEDS = (37, 38)
FATAL_PATTERN = re.compile(
    r"traceback|segmentation fault|fatal error|connection closed by sumo|"
    r"process exited with code [1-9]|\berror:\s",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
    return hasher.hexdigest()


def last_runtime_time(path: Path) -> float:
    last = None
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                last = json.loads(line)
    if last is None:
        raise RuntimeError(f"empty runtime log: {path}")
    for key in ("simulation_time_s", "simulation_time", "sim_time_s", "sim_time"):
        if key in last:
            return float(last[key])
    raise RuntimeError(f"runtime record lacks simulation time: {path}")


def fcd_end_time(path: Path) -> float | None:
    last = None
    with gzip.open(path, "rb") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag == "timestep":
                last = float(element.attrib["time"])
            element.clear()
    return last


def group_total(metrics, field: str) -> float:
    return sum(
        float(metrics.get("groups", {}).get(group, {}).get(field, 0.0))
        for group in ("car", "bus")
    )


def summary_value(stderr: str, name: str) -> float:
    match = re.search(rf"^{name}\s*:\s*([0-9.eE+-]+)", stderr, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"missing {name} in stderr")
    return float(match.group(1))


def analyze_run(
    output_root: Path,
    source_root: Path,
    source_commit: str,
    value: float,
    seed: int,
):
    tag = "lambda0525" if math.isclose(value, 0.525) else "lambda095"
    run = output_root / tag / "eval7" / f"seed-{seed}"
    required = (
        "manifest.json",
        "evaluation-metrics.json",
        "tiv-audit.json",
        "physical-collisions.jsonl",
        "stdout.log",
        "stderr.log",
        "runtime.jsonl",
        "fcd.xml.gz",
        "negotiations.jsonl",
        "conflicts.jsonl",
        "vehicle-states.jsonl",
        "prediction-events.jsonl",
        "deceleration-audit.json",
    )
    missing = [name for name in required if not (run / name).is_file()]
    if missing:
        raise RuntimeError(f"{run}: missing {missing}")
    manifest = json.loads((run / "manifest.json").read_text())
    metrics = json.loads((run / "evaluation-metrics.json").read_text())
    fixed = manifest["fixed_vehicle_input"]
    fixed_path = source_root / fixed["path"]
    stdout = (run / "stdout.log").read_text(errors="replace")
    stderr = (run / "stderr.log").read_text(errors="replace")
    prediction = manifest.get("deceleration_prediction") or {}
    checks = {
        "exit_code": manifest.get("exit_code") == 0,
        "source_unchanged": manifest.get("source_unchanged") is True,
        "source_commit": manifest.get("git", {}).get("commit") == source_commit,
        "git_clean": manifest.get("git", {}).get("dirty") is False,
        "case": manifest.get("case") == "eval7",
        "seed": manifest.get("seed") == seed,
        "flows": manifest.get("flows_vph") == {
            "requesting": 700,
            "accepting": 1000,
        },
        "duration": manifest.get("input_duration") == 600.0,
        "lambda": math.isclose(
            float(prediction.get("convex_lambda", -1)), value
        ),
        "diagnostic_traces": manifest.get("diagnostic_traces_enabled") is True,
        "checkpoint_disabled": manifest.get("checkpointing") is None,
        "fixed_input_exists": fixed_path.is_file(),
        "fixed_input_sha256": (
            fixed_path.is_file() and sha256(fixed_path) == fixed.get("sha256")
        ),
        "python": str(manifest.get("python_version", "")).startswith("3.15.1"),
        "sumo": "1.28.0" in str(manifest.get("sumo_version", "")).splitlines()[0],
        "runtime_end": math.isclose(
            last_runtime_time(run / "runtime.jsonl"), 600.0, abs_tol=0.011
        ),
        "fcd_end": math.isclose(
            float(fcd_end_time(run / "fcd.xml.gz")), 599.9, abs_tol=0.011
        ),
        "collision_free": (
            metrics["physical_safety"]["unique_collision_episodes"] == 0
        ),
        "collision_log_empty": (
            (run / "physical-collisions.jsonl").stat().st_size == 0
        ),
        "fatal_logs": FATAL_PATTERN.search(stderr + "\n" + stdout) is None,
    }
    return {
        "lambda": value,
        "seed": seed,
        "all_speed_mps": float(manifest["all_speed_mps"]),
        "requesting_speed_mps": summary_value(stderr, "requesting_speed"),
        "accepting_speed_mps": summary_value(stderr, "accepting_speed"),
        "stop_time_s": group_total(metrics, "stop_time_s"),
        "hard_brake_time_s": group_total(metrics, "hard_brake_time_s"),
        "physical_collision_episodes": metrics["physical_safety"][
            "unique_collision_episodes"
        ],
        "fixed_input_sha256": fixed["sha256"],
        "checks": checks,
        "errors": [name for name, passed in checks.items() if not passed],
    }


def build_summary(rows, source_commit: str):
    paired = []
    for seed in SEEDS:
        low = next(
            row for row in rows if row["seed"] == seed and row["lambda"] == 0.525
        )
        high = next(
            row for row in rows if row["seed"] == seed and row["lambda"] == 0.95
        )
        if low["fixed_input_sha256"] != high["fixed_input_sha256"]:
            raise RuntimeError(f"seed-{seed}: fixed input mismatch")
        paired.append(
            {
                "seed": seed,
                "all_speed_difference_mps": (
                    high["all_speed_mps"] - low["all_speed_mps"]
                ),
                "requesting_speed_difference_mps": (
                    high["requesting_speed_mps"] - low["requesting_speed_mps"]
                ),
                "accepting_speed_difference_mps": (
                    high["accepting_speed_mps"] - low["accepting_speed_mps"]
                ),
                "stop_time_difference_s": high["stop_time_s"] - low["stop_time_s"],
            }
        )
    return {
        "schema_version": 1,
        "experiment_id": "eval7-lambda-merge-delay-20261127",
        "classification": "diagnostic",
        "source_commit": source_commit,
        "run_count": len(rows),
        "ok": all(not row["errors"] for row in rows),
        "runs": rows,
        "paired": paired,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    rows = [
        analyze_run(
            args.output_root.resolve(),
            args.source_root.resolve(),
            args.source_commit,
            value,
            seed,
        )
        for value in LAMBDAS
        for seed in SEEDS
    ]
    summary = build_summary(rows, args.source_commit)
    output = args.output_root.resolve() / "diagnostic-audit.json"
    output.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary, allow_nan=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

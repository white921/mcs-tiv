#!/usr/bin/env python3
"""Run the gated 15-slot intersection lane-heading fallback ablation."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_thesis_batch.py"
LAMBDA = 0.95
MIN_RETAINED_DETAILS = 20
MIN_PATTERN_FRACTION = 0.80

SPECS = (
    {
        "name": "eval3-500-seeds13-17",
        "case": "eval3",
        "seeds": (13, 14, 15, 16, 17),
        "flows": (500, 500, 500),
        "fixed_input": (
            "fixed_inputs/thesis/eval35-paper-comparison/"
            "eval3-500/seed-{seed}.jsonl"
        ),
    },
    {
        "name": "eval5-300-seeds13-17",
        "case": "eval5",
        "seeds": (13, 14, 15, 16, 17),
        "flows": (300, 300, 300, 300),
        "fixed_input": (
            "fixed_inputs/thesis/eval35-paper-comparison/"
            "eval5-300/seed-{seed}.jsonl"
        ),
    },
    {
        "name": "eval5-300-seeds18-22",
        "case": "eval5",
        "seeds": (18, 19, 20, 21, 22),
        "flows": (300, 300, 300, 300),
        "fixed_input": (
            "fixed_inputs/thesis/eval35-paper-comparison/"
            "eval5-300/seed-{seed}.jsonl"
        ),
    },
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()


def active_sumo_count() -> int:
    result = subprocess.run(
        ["pgrep", "-x", "sumo"], text=True, capture_output=True, check=False
    )
    if result.returncode == 1:
        return 0
    if result.returncode != 0:
        raise RuntimeError("pgrep -x sumo failed: " + result.stderr.strip())
    return len([line for line in result.stdout.splitlines() if line.strip()])


def gate_report(baseline_summary: Path) -> dict[str, object]:
    report = json.loads(baseline_summary.read_text(encoding="utf-8"))
    if report.get("analysis") != "topology-heading-attribution-diagnostic":
        raise RuntimeError("unexpected baseline analysis")
    if report.get("validated_run_count") != 15:
        raise RuntimeError("baseline must validate exactly 15 runs")
    if report.get("physical_collision_count") != 0:
        raise RuntimeError("baseline contains a physical collision")
    conditions = report.get("conditions", {})
    selected = [
        conditions.get("eval3:500-500-500"),
        conditions.get("eval5:300-300-300-300"),
    ]
    if any(not isinstance(item, dict) for item in selected):
        raise RuntimeError("baseline intersection conditions are missing")
    details = sum(item["retained_with_details"] for item in selected)
    stationary = sum(item["stationary_without_yaw"] for item in selected)
    lane_positions = sum(item["lane_position_present"] for item in selected)
    unknown_lanes = sum(item.get("lane_id", {}).get("unknown", 0)
                        for item in selected)
    if details < MIN_RETAINED_DETAILS:
        raise RuntimeError("too few attributed unsupported records")
    stationary_fraction = stationary / details
    lane_position_fraction = lane_positions / details
    known_lane_fraction = 1 - unknown_lanes / details
    if stationary_fraction < MIN_PATTERN_FRACTION:
        raise RuntimeError("stationary-without-yaw pattern is not dominant")
    if lane_position_fraction < MIN_PATTERN_FRACTION:
        raise RuntimeError("lane position coverage is insufficient")
    if known_lane_fraction < MIN_PATTERN_FRACTION:
        raise RuntimeError("lane identity coverage is insufficient")
    return {
        "eligible": True,
        "retained_with_details": details,
        "stationary_without_yaw_fraction": stationary_fraction,
        "lane_position_present_fraction": lane_position_fraction,
        "known_lane_fraction": known_lane_fraction,
        "minimum_required_fraction": MIN_PATTERN_FRACTION,
    }


def output_path(output_root: Path, spec: dict[str, object]) -> Path:
    return output_root / (
        f"intersection-lane-heading-fallback-{spec['name']}-300s-20261128"
    )


def command(
    output_root: Path, sumo_home: Path, python: str, spec: dict[str, object]
) -> list[str]:
    return [
        python,
        str(RUNNER),
        "--sumo-home", str(sumo_home),
        "--output", str(output_path(output_root, spec)),
        "--cases", str(spec["case"]),
        "--workers", "5",
        "--seeds", *(str(seed) for seed in spec["seeds"]),
        "--duration", "300",
        "--case-flows", *(str(flow) for flow in spec["flows"]),
        "--bus-allocation", "fixed",
        "--fixed-input-override", str(spec["fixed_input"]),
        "--deceleration-active",
        "--deceleration-convex-lambda", str(LAMBDA),
        "--deceleration-lane-metadata-heading-fallback",
        "--diagnostic-traces",
        "--checkpoint-interval", "60",
    ]


def preflight(
    output_root: Path, sumo_home: Path, python: str, baseline_summary: Path
) -> dict[str, object]:
    status = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain=v1"], text=True
    )
    if status.strip():
        raise RuntimeError("source worktree must be clean before launch")
    if not (sumo_home / "bin" / "sumo").is_file():
        raise RuntimeError("SUMO bin/sumo is missing")
    if not (sumo_home / "tools" / "traci" / "__init__.py").is_file():
        raise RuntimeError("SUMO tools/traci is missing")
    env = dict(os.environ, PYTHONPATH=str(sumo_home / "tools"))
    subprocess.run([python, "-c", "import traci"], env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if active_sumo_count() != 0:
        raise RuntimeError("another SUMO process is already active")
    if output_root.exists():
        raise RuntimeError(f"output root already exists: {output_root}")
    for spec in SPECS:
        missing = [
            str(spec["fixed_input"]).format(seed=seed)
            for seed in spec["seeds"]
            if not (ROOT / str(spec["fixed_input"]).format(seed=seed)).is_file()
        ]
        if missing:
            raise RuntimeError("missing fixed inputs: " + ", ".join(missing))
    return {
        "ok": True,
        "source_commit": source_commit(),
        "classification": "diagnostic-ablation",
        "behavior_change": "lane-metadata-heading-fallback-only",
        "baseline_summary": str(baseline_summary.resolve()),
        "gate": gate_report(baseline_summary),
        "machine_workers": 15,
        "cohorts": [{
            "name": spec["name"], "case": spec["case"],
            "seeds": list(spec["seeds"]), "flows_vph": list(spec["flows"]),
            "workers": 5, "output": str(output_path(output_root, spec)),
            "command": command(output_root, sumo_home, python, spec),
        } for spec in SPECS],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    report = preflight(output_root, args.sumo_home.resolve(), args.python,
                       args.baseline_summary.resolve())
    if args.preflight_only:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    output_root.mkdir(parents=True)
    report.update(status="running", automatic_rerun=False,
                  started_at=dt.datetime.now().astimezone().isoformat())
    manifest = output_root / "experiment-manifest.json"
    write_json(manifest, report)
    processes = []
    for spec in SPECS:
        log = output_root / f"{spec['name']}.scheduler.log"
        stream = log.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command(output_root, args.sumo_home.resolve(), args.python, spec),
            cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, text=True)
        processes.append((spec, process, stream, log))
    results = []
    for spec, process, stream, log in processes:
        returncode = process.wait()
        stream.close()
        results.append({"name": spec["name"], "returncode": returncode,
                        "log": str(log)})
    failed = [item for item in results if item["returncode"] != 0]
    report.update(status="failed" if failed else "completed", results=results,
                  finished_at=dt.datetime.now().astimezone().isoformat())
    write_json(manifest, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run two 15-slot outcome-specific decision-lock intersection waves."""
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

ARMS = (
    {
        "name": "accept-short-reject-long",
        "accept_lock_s": 0.1,
        "reject_lock_s": 1.0,
    },
    {
        "name": "accept-long-reject-short",
        "accept_lock_s": 1.0,
        "reject_lock_s": 0.1,
    },
)

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


def cadence_gate(summary_path: Path) -> dict[str, object]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("analysis") != "intersection-decision-lock-cadence-ablation":
        raise RuntimeError("unexpected cadence summary")
    if summary.get("physical_collision_count") != 0:
        raise RuntimeError("cadence batch contains a physical collision")
    if summary.get("validated_baseline_run_count") != 15:
        raise RuntimeError("cadence summary must validate 15 baseline runs")
    if summary.get("validated_short_lock_run_count") != 15:
        raise RuntimeError("cadence summary must validate 15 short-lock runs")
    if summary.get("cadence_hypothesis", {}).get("supported") is not False:
        raise RuntimeError("factorial requires the common-cadence hypothesis to fail")
    return {
        "eligible": True,
        "common_cadence_supported": False,
        "cadence_summary": str(summary_path),
    }


def output_path(output_root: Path, arm: dict[str, object],
                spec: dict[str, object]) -> Path:
    return output_root / str(arm["name"]) / (
        f"intersection-{arm['name']}-{spec['name']}-300s-20261129"
    )


def command(output_root: Path, sumo_home: Path, python: str,
            arm: dict[str, object], spec: dict[str, object]) -> list[str]:
    return [
        python,
        str(RUNNER),
        "--sumo-home", str(sumo_home),
        "--output", str(output_path(output_root, arm, spec)),
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
        "--deceleration-decision-lock-seconds", "1.0",
        "--deceleration-decision-lock-accept-seconds",
        str(arm["accept_lock_s"]),
        "--deceleration-decision-lock-reject-seconds",
        str(arm["reject_lock_s"]),
        "--diagnostic-traces",
        "--checkpoint-interval", "60",
    ]


def preflight(output_root: Path, sumo_home: Path, python: str,
              cadence_summary: Path) -> dict[str, object]:
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
    subprocess.run(
        [python, "-c", "import traci"], env=env, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
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
        "classification": "diagnostic-factorial-ablation",
        "behavior_change": "outcome-specific-active-decision-lock",
        "gate": cadence_gate(cadence_summary),
        "machine_workers": 15,
        "automatic_rerun": False,
        "wave_order": [arm["name"] for arm in ARMS],
        "arms": [{
            **arm,
            "cohorts": [{
                "name": spec["name"], "case": spec["case"],
                "seeds": list(spec["seeds"]),
                "flows_vph": list(spec["flows"]),
                "workers": 5,
                "output": str(output_path(output_root, arm, spec)),
                "command": command(output_root, sumo_home, python, arm, spec),
            } for spec in SPECS],
        } for arm in ARMS],
    }


def run_wave(output_root: Path, sumo_home: Path, python: str,
             arm: dict[str, object]) -> list[dict[str, object]]:
    processes = []
    for spec in SPECS:
        log = output_root / f"{arm['name']}-{spec['name']}.scheduler.log"
        stream = log.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command(output_root, sumo_home, python, arm, spec),
            cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, text=True,
        )
        processes.append((spec, process, stream, log))
    results = []
    for spec, process, stream, log in processes:
        returncode = process.wait()
        stream.close()
        results.append({
            "name": spec["name"], "returncode": returncode, "log": str(log),
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cadence-summary", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    report = preflight(
        output_root, args.sumo_home.resolve(), args.python,
        args.cadence_summary.resolve(),
    )
    if args.preflight_only:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    output_root.mkdir(parents=True)
    report.update(
        status="running", started_at=dt.datetime.now().astimezone().isoformat(),
        completed_waves=[],
    )
    manifest = output_root / "experiment-manifest.json"
    write_json(manifest, report)
    for arm in ARMS:
        results = run_wave(
            output_root, args.sumo_home.resolve(), args.python, arm)
        wave = {"arm": arm["name"], "results": results}
        report["completed_waves"].append(wave)
        if any(item["returncode"] != 0 for item in results):
            report.update(
                status="failed",
                finished_at=dt.datetime.now().astimezone().isoformat(),
            )
            write_json(manifest, report)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 1
        write_json(manifest, report)
    report.update(
        status="completed",
        finished_at=dt.datetime.now().astimezone().isoformat(),
    )
    write_json(manifest, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

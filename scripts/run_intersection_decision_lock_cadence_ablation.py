#!/usr/bin/env python3
"""Run the 15-slot intersection proposal decision-lock cadence ablation."""
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
DECISION_LOCK_S = 0.1

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


def baseline_gate(summary_path: Path) -> dict[str, object]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("analysis") != "intersection-lane-heading-fallback-ablation":
        raise RuntimeError("unexpected baseline summary")
    if summary.get("physical_collision_count") != 0:
        raise RuntimeError("baseline contains a physical collision")
    if summary.get("validated_ablation_run_count") != 15:
        raise RuntimeError("baseline must validate exactly 15 fallback runs")
    gate = summary.get("advancement_gate", {})
    if gate.get("mechanism_supported") is not True:
        raise RuntimeError("heading mechanism gate did not pass")
    if gate.get("performance_signal_supported") is not False:
        raise RuntimeError("cadence diagnostic requires the failed performance gate")
    return {
        "eligible": True,
        "heading_mechanism_supported": True,
        "heading_performance_signal_supported": False,
        "baseline_summary": str(summary_path),
    }


def output_path(output_root: Path, spec: dict[str, object]) -> Path:
    return output_root / (
        f"intersection-decision-lock-cadence-{spec['name']}-300s-20261129"
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
        "--deceleration-decision-lock-seconds", str(DECISION_LOCK_S),
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
        "classification": "diagnostic-ablation",
        "behavior_change": "active-decision-lock-1.0s-to-0.1s-only",
        "gate": baseline_gate(baseline_summary),
        "machine_workers": 15,
        "automatic_rerun": False,
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
    report = preflight(
        output_root, args.sumo_home.resolve(), args.python,
        args.baseline_summary.resolve(),
    )
    if args.preflight_only:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    output_root.mkdir(parents=True)
    report.update(
        status="running", started_at=dt.datetime.now().astimezone().isoformat())
    manifest = output_root / "experiment-manifest.json"
    write_json(manifest, report)
    processes = []
    for spec in SPECS:
        log = output_root / f"{spec['name']}.scheduler.log"
        stream = log.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command(output_root, args.sumo_home.resolve(), args.python, spec),
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
    failed = [item for item in results if item["returncode"] != 0]
    report.update(
        status="failed" if failed else "completed", results=results,
        finished_at=dt.datetime.now().astimezone().isoformat(),
    )
    write_json(manifest, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

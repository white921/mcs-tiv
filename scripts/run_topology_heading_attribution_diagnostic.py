#!/usr/bin/env python3
"""Run the 15-slot topology heading-attribution diagnostic.

The three five-seed cohorts start together.  This is an instrumentation-only
diagnostic: the proposal decision rule and fallback to TIVtep are unchanged.
"""
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

SPECS = (
    {
        "name": "eval3-500",
        "case": "eval3",
        "seeds": (13, 14, 15, 16, 17),
        "flows": (500, 500, 500),
        "fixed_input": (
            "fixed_inputs/thesis/eval35-paper-comparison/"
            "eval3-500/seed-{seed}.jsonl"
        ),
    },
    {
        "name": "eval5-300",
        "case": "eval5",
        "seeds": (13, 14, 15, 16, 17),
        "flows": (300, 300, 300, 300),
        "fixed_input": (
            "fixed_inputs/thesis/eval35-paper-comparison/"
            "eval5-300/seed-{seed}.jsonl"
        ),
    },
    {
        "name": "eval7-1000",
        "case": "eval7",
        "seeds": (33, 34, 35, 36, 37),
        "flows": (1000, 1000),
        "fixed_input": (
            "fixed_inputs/thesis/eval7-flow-sweep/"
            "requesting-1000-accepting-1000/seed-{seed}.jsonl"
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


def source_status() -> list[str]:
    output = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain=v1"], text=True
    )
    return output.splitlines()


def active_sumo_count() -> int:
    result = subprocess.run(
        ["pgrep", "-x", "sumo"], text=True, capture_output=True, check=False
    )
    if result.returncode == 1:
        return 0
    if result.returncode != 0:
        raise RuntimeError("pgrep -x sumo failed: " + result.stderr.strip())
    return len([line for line in result.stdout.splitlines() if line.strip()])


def output_path(output_root: Path, spec: dict[str, object]) -> Path:
    seeds = spec["seeds"]
    return output_root / (
        f"topology-heading-attribution-{spec['name']}-"
        f"seeds{seeds[0]}-{seeds[-1]}-300s-20261128"
    )


def command(
    output_root: Path, sumo_home: Path, python: str, spec: dict[str, object]
) -> list[str]:
    result = [
        python,
        str(RUNNER),
        "--sumo-home",
        str(sumo_home),
        "--output",
        str(output_path(output_root, spec)),
        "--cases",
        str(spec["case"]),
        "--workers",
        "5",
        "--seeds",
        *(str(seed) for seed in spec["seeds"]),
        "--duration",
        "300",
        "--case-flows" if spec["case"] != "eval7" else "--eval7-flows",
        *(str(flow) for flow in spec["flows"]),
        "--bus-allocation",
        "fixed",
        "--deceleration-active",
        "--deceleration-convex-lambda",
        str(LAMBDA),
        "--diagnostic-traces",
        "--checkpoint-interval",
        "60",
    ]
    if spec["fixed_input"] is not None:
        result.extend(["--fixed-input-override", str(spec["fixed_input"])])
    return result


def preflight(output_root: Path, sumo_home: Path, python: str) -> dict[str, object]:
    if source_status():
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
        pattern = spec["fixed_input"]
        missing = [
            str(pattern).format(seed=seed)
            for seed in spec["seeds"]
            if not (ROOT / str(pattern).format(seed=seed)).is_file()
        ]
        if missing:
            raise RuntimeError("missing fixed inputs: " + ", ".join(missing))
    return {
        "ok": True,
        "source_commit": source_commit(),
        "active_sumo": 0,
        "cohorts": [
            {
                "name": spec["name"],
                "case": spec["case"],
                "seeds": list(spec["seeds"]),
                "flows_vph": list(spec["flows"]),
                "workers": 5,
                "output": str(output_path(output_root, spec)),
                "command": command(output_root, sumo_home, python, spec),
            }
            for spec in SPECS
        ],
        "machine_workers": 15,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    report = preflight(output_root, args.sumo_home.resolve(), args.python)
    if args.preflight_only:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    output_root.mkdir(parents=True)
    report.update(
        status="running",
        classification="diagnostic",
        started_at=dt.datetime.now().astimezone().isoformat(),
        behavior_change=False,
        automatic_rerun=False,
    )
    manifest = output_root / "experiment-manifest.json"
    write_json(manifest, report)
    processes = []
    for spec in SPECS:
        log = output_root / f"{spec['name']}.scheduler.log"
        stream = log.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command(output_root, args.sumo_home.resolve(), args.python, spec),
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
        processes.append((spec, process, stream, log))

    results = []
    for spec, process, stream, log in processes:
        returncode = process.wait()
        stream.close()
        results.append(
            {"name": spec["name"], "returncode": returncode, "log": str(log)}
        )
    failed = [item for item in results if item["returncode"] != 0]
    report.update(
        status="failed" if failed else "completed",
        finished_at=dt.datetime.now().astimezone().isoformat(),
        results=results,
    )
    write_json(manifest, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

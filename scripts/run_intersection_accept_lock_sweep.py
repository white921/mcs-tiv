#!/usr/bin/env python3
"""Run three 15-slot waves of intermediate Accept decision-lock periods."""
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
ACCEPT_LOCKS_S = (0.3, 0.5, 0.7)
REJECT_LOCK_S = 1.0

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


def degeneracy_gate(summary_path: Path) -> dict[str, object]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("analysis") != "intersection-decision-outcome-lock-degeneracy":
        raise RuntimeError("unexpected outcome-lock degeneracy summary")
    if summary.get("physical_collision_count") != 0:
        raise RuntimeError("outcome-lock diagnostic contains a collision")
    if summary.get("validated_run_count") != 45:
        raise RuntimeError("degeneracy summary must validate 45 runs")
    if summary.get("validated_new_run_count") != 15:
        raise RuntimeError("degeneracy summary must validate 15 new runs")
    evidence = summary.get("reject_lock_degeneracy", {})
    if evidence.get("supported") is not True:
        raise RuntimeError("Reject-lock degeneracy was not established")
    if evidence.get("exact_record_matches") != 15:
        raise RuntimeError("outcome-lock equivalence must cover all 15 runs")
    return {
        "eligible": True,
        "reject_lock_degenerate": True,
        "degeneracy_summary": str(summary_path),
    }


def lock_label(value: float) -> str:
    return str(value).replace(".", "p")


def output_path(output_root: Path, accept_lock_s: float,
                spec: dict[str, object]) -> Path:
    return output_root / f"accept-lock-{lock_label(accept_lock_s)}s" / (
        f"intersection-accept-lock-{lock_label(accept_lock_s)}s-"
        f"{spec['name']}-300s-20261129"
    )


def command(output_root: Path, sumo_home: Path, python: str,
            accept_lock_s: float, spec: dict[str, object]) -> list[str]:
    return [
        python,
        str(RUNNER),
        "--sumo-home", str(sumo_home),
        "--output", str(output_path(output_root, accept_lock_s, spec)),
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
        "--deceleration-decision-lock-accept-seconds", str(accept_lock_s),
        "--deceleration-decision-lock-reject-seconds", str(REJECT_LOCK_S),
        "--diagnostic-traces",
        "--checkpoint-interval", "60",
    ]


def preflight(output_root: Path, sumo_home: Path, python: str,
              degeneracy_summary: Path) -> dict[str, object]:
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
        "classification": "diagnostic-accept-lock-sweep",
        "behavior_change": "intermediate-accept-decision-lock",
        "gate": degeneracy_gate(degeneracy_summary),
        "machine_workers": 15,
        "automatic_rerun": False,
        "wave_order_s": list(ACCEPT_LOCKS_S),
        "waves": [{
            "accept_lock_s": value,
            "reject_lock_s": REJECT_LOCK_S,
            "cohorts": [{
                "name": spec["name"], "case": spec["case"],
                "seeds": list(spec["seeds"]),
                "flows_vph": list(spec["flows"]),
                "workers": 5,
                "output": str(output_path(output_root, value, spec)),
                "command": command(output_root, sumo_home, python, value, spec),
            } for spec in SPECS],
        } for value in ACCEPT_LOCKS_S],
    }


def run_wave(output_root: Path, sumo_home: Path, python: str,
             accept_lock_s: float) -> list[dict[str, object]]:
    processes = []
    for spec in SPECS:
        log = output_root / (
            f"accept-lock-{lock_label(accept_lock_s)}s-{spec['name']}.scheduler.log"
        )
        stream = log.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command(output_root, sumo_home, python, accept_lock_s, spec),
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
    parser.add_argument("--degeneracy-summary", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    report = preflight(
        output_root, args.sumo_home.resolve(), args.python,
        args.degeneracy_summary.resolve(),
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
    for accept_lock_s in ACCEPT_LOCKS_S:
        results = run_wave(
            output_root, args.sumo_home.resolve(), args.python, accept_lock_s)
        report["completed_waves"].append({
            "accept_lock_s": accept_lock_s,
            "results": results,
        })
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

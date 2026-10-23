#!/usr/bin/env python3
"""Run paper cases in isolated directories with bounded parallelism.

Each task is one scenario/method/seed combination.  A task owns a copy of the
source files it can modify at runtime, so several SUMO processes never race on
route files or historical statistics CSVs.  This runner deliberately keeps the
paper-facing settings intact: 600 simulated seconds, the documented seed sets,
one-second candidate trajectory regeneration in ``thesis`` mode, and
per-vehicle 25% bus draws where applicable.  SUMO and MCM still advance every
0.1 seconds.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SPEED = re.compile(r"^all_speed\s*:\s*(\S+)\s*$", re.MULTILINE)
MIX = re.compile(r"^vehicle_mix\s*:\s*Bus\s+(\d+)\s+Car\s+(\d+)", re.MULTILINE)

# These are the five published result families for which the audited source
# contains an exact scenario runner.  Eval.1/2 need their comparison matrices
# audited separately before they can be called paper reproductions.
CASES = {
    "eval3": {
        "folder": "junction", "script": "junction_three_agree.py", "alpha": "7",
        "flows": ["400", "400", "400"], "bus_share": "0.25",
        "seeds": [1, 2, 3, 4, 5], "reference": 7.4159,
    },
    "eval4": {
        "folder": "junction", "script": "junction_four_agree.py", "alpha": "6",
        "flows": ["300", "300", "300", "300"], "bus_share": "0",
        "seeds": [1, 3, 5, 6, 7], "reference": 7.2485,
    },
    "eval5": {
        "folder": "junction", "script": "junction_four_agree.py", "alpha": "7",
        "flows": ["300", "300", "300", "300"], "bus_share": "0.25",
        "seeds": [1, 2, 3, 4, 5], "reference": 6.4420,
    },
    "eval6": {
        "folder": "merge", "script": "merge_agree2512.py", "alpha": "6",
        "flows": ["1000", "1000"], "bus_share": "0",
        "seeds": [1, 2, 3, 6, 8], "reference": 4.8032,
    },
    "eval7": {
        "folder": "merge", "script": "merge_agree2512.py", "alpha": "7",
        "flows": ["1000", "1000"], "bus_share": "0.25",
        "seeds": [1, 2, 3, 7, 11], "reference": 4.2084,
    },
}


def source_hashes(source):
    return {
        str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source.rglob("*")
        if path.is_file() and path.suffix in (".py", ".xml", ".sumocfg")
    }


def prepare_source(destination, case):
    source = destination / "source"
    source.mkdir()
    for name in ("func", "PathPlanning", "junction", "merge"):
        shutil.copytree(ROOT / name, source / name, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "statistics", "results*", "*.log"))
    for name in ("junction", "merge"):
        (source / name / "statistics").mkdir()
    return source, source_hashes(source)


def run_task(task, args):
    name, seed = task
    case = CASES[name]
    destination = args.output / name / ("seed-" + str(seed))
    destination.mkdir(parents=True, exist_ok=False)
    source, initial_hashes = prepare_source(destination, case)
    sumo_home = args.sumo_home.resolve()
    if args.deceleration_active and not (case["folder"] == "junction" and case["script"] == "junction_three_agree.py"):
        raise ValueError("deceleration-active is currently implemented and validated for eval3 (T junction) only")
    env = dict(os.environ,
               SUMO_HOME=str(sumo_home),
               PYTHONPATH=str(sumo_home / "tools"),
               MPLBACKEND="Agg", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MCS_TIV_IMPLEMENTATION="thesis",
               MCS_TIV_AUDIT=str(destination / "tiv-audit.json"))
    if args.deceleration_active:
        env["MCS_DECELERATION_AUDIT"] = str(destination / "deceleration-audit.json")
    command = [args.python, "-u", case["script"], case["alpha"], str(seed),
               *case["flows"], "--nogui", "--quiet", "--duration", "600",
               "--bus-allocation", "paper-random25"]
    is_three_way = case["folder"] == "junction" and case["script"] == "junction_three_agree.py"
    if args.deceleration_active:
        command.append("--deceleration-active")
    if not is_three_way:
        command += ["--bus-share", case["bus_share"]]
        command.append("--no-save")
    if args.stop_time is not None:
        command += ["--stop-time", str(args.stop_time)]
    manifest = {
        "case": name, "seed": seed, "command": command,
        "input_duration": 600, "stop_time": args.stop_time or 600,
        "paper_reference_mean_mps": case["reference"],
        "decision_method": "deceleration-propagation" if args.deceleration_active else "thesis-tiv",
        "source_sha256": initial_hashes,
        "sumo_version": subprocess.check_output([str(sumo_home / "bin" / "sumo"), "--version"], text=True),
        "started_epoch": time.time(),
    }
    if args.paper is not None:
        manifest["paper_sha256"] = hashlib.sha256(args.paper.read_bytes()).hexdigest()
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    started = time.monotonic()
    with (destination / "stdout.log").open("w") as stdout, (destination / "stderr.log").open("w") as stderr:
        process = subprocess.run(command, cwd=source / case["folder"], env=env,
                                 stdout=stdout, stderr=stderr)
    # ``--quiet`` deliberately sends the final summary to stderr, while the
    # verbose stream is redirected to /dev/null inside the scenario runner.
    output = ((destination / "stdout.log").read_text(errors="replace") + "\n" +
              (destination / "stderr.log").read_text(errors="replace"))
    speed = SPEED.search(output)
    mix = MIX.search(output)
    manifest.update(exit_code=process.returncode, elapsed_seconds=time.monotonic() - started,
                    source_unchanged=(initial_hashes == source_hashes(source)),
                    all_speed_mps=(float(speed.group(1)) if speed else None),
                    vehicle_mix=([int(mix.group(1)), int(mix.group(2))] if mix else None),
                    audit_written=(destination / "tiv-audit.json").is_file(),
                    deceleration_audit_written=(destination / "deceleration-audit.json").is_file())
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", choices=CASES, nargs="+", default=list(CASES))
    parser.add_argument("--workers", type=int, default=3,
                        help="independent SUMO tasks; use 3-4, not all CPU threads")
    parser.add_argument("--seeds-per-case", type=int,
                        help="run only this many leading documented seeds per case (smoke tests)")
    parser.add_argument("--stop-time", type=float,
                        help="smoke test only; retains 600-second input schedule")
    parser.add_argument("--paper", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--deceleration-active", action="store_true",
                        help="use the proposed deceleration-propagation rule (Eval.3 only)")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.seeds_per_case is not None and args.seeds_per_case < 1:
        parser.error("--seeds-per-case must be positive")
    if args.stop_time is not None and not 0 < args.stop_time <= 600:
        parser.error("--stop-time must be in (0, 600]")
    if not (args.sumo_home / "bin" / "sumo").is_file() or not (args.sumo_home / "tools" / "traci").is_dir():
        parser.error("--sumo-home must contain bin/sumo and tools/traci")
    if args.paper is not None and not args.paper.is_file():
        parser.error("--paper must name an existing PDF")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    tasks = [(name, seed) for name in args.cases
             for seed in CASES[name]["seeds"][:args.seeds_per_case]]
    print(json.dumps({"tasks": len(tasks), "workers": args.workers, "output": str(args.output)}), flush=True)
    reports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_task = {pool.submit(run_task, task, args): task for task in tasks}
        for future in concurrent.futures.as_completed(future_to_task):
            task = future_to_task[future]
            try:
                report = future.result()
            except Exception as error:  # preserve other completed task evidence
                report = {"case": task[0], "seed": task[1], "error": repr(error)}
            reports.append(report)
            print(json.dumps({key: report.get(key) for key in ("case", "seed", "exit_code", "elapsed_seconds", "all_speed_mps", "error")}), flush=True)
    reports.sort(key=lambda report: (report["case"], report["seed"]))
    (args.output / "summary.json").write_text(json.dumps(reports, indent=2, allow_nan=False))
    failures = [report for report in reports if report.get("exit_code") != 0]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

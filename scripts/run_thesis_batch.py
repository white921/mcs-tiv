#!/usr/bin/env python3
"""Run paper cases in isolated directories with bounded parallelism.

Each task is one scenario/method/seed combination.  A task owns a copy of the
source files it can modify at runtime, so several SUMO processes never race on
route files or historical statistics CSVs.  This runner deliberately keeps the
comparison settings fixed: an explicitly selected simulated duration (600 s
for final evaluation or 300 s for diagnostics), the documented seed sets,
one-second candidate trajectory regeneration in ``thesis`` mode, and a fixed
25% bus composition where applicable.  Eval.3/5/7 use prefixes of committed
600-second vehicle-event files for fixed-allocation runs up to 600 seconds.
SUMO and MCM still advance every
0.1 seconds.  ``paper-random25`` remains available only when reproducing the
original artifact's per-vehicle random draw.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
from fixed_vehicle_inputs import load_fixed_vehicle_input  # noqa: E402

SPEED = re.compile(r"^all_speed\s*:\s*(\S+)\s*$", re.MULTILINE)
MIX = re.compile(r"^vehicle_mix\s*:\s*Bus\s+(\d+)\s+Car\s+(\d+)", re.MULTILINE)

# Shared instrumentation only: remove all controls capable of changing a
# decision before launching each isolated simulation.
CONTROLLED_MCS_ENV = {
    "MCS_CHECKPOINT_DIR", "MCS_CHECKPOINT_INTERVAL", "MCS_CONFLICT_AUDIT",
    "MCS_DECELERATION_AUDIT", "MCS_DECELERATION_MODE",
    "MCS_DECELERATION_LOSS_LAMBDA", "MCS_DECELERATION_TIME_HALF_LIFE_S",
    "MCS_EVALUATION_AUDIT", "MCS_FCD_OUTPUT", "MCS_NEGOTIATION_AUDIT",
    "MCS_PHYSICAL_COLLISION_AUDIT", "MCS_PREDICTION_EVENT_AUDIT",
    "MCS_PRIORITY_HOLD_ACTIVATION_SPEED", "MCS_PRIORITY_HOLD_MAX_DURATION",
    "MCS_PRIORITY_HOLD_MODE", "MCS_PRIORITY_HOLD_PROGRESS_TIMEOUT",
    "MCS_PRIORITY_HOLD_QUEUE_GROWTH_LIMIT", "MCS_RUNTIME_AUDIT",
    "MCS_TIV_AUDIT", "MCS_TIV_IMPLEMENTATION", "MCS_VEHICLE_STATE_AUDIT",
}


def clean_experiment_environment():
    env = dict(os.environ)
    for name in CONTROLLED_MCS_ENV:
        env.pop(name, None)
    return env


TIV_SCORING_MANIFEST = {
    "implementation": "environment-trapezoid-10s-v1",
    "environment_term": "trapezoid integral of 0.1-second speed samples",
    "horizon_s": 10.0, "step_s": 0.1, "endpoints": 101, "intervals": 100,
    "short_trajectory_completion": "terminal predicted speed",
    "environment_coefficient": 0.1, "performance_term": "disabled (0.0)",
}

# These are the five published result families for which the audited source
# contains an exact scenario runner.  Eval.1/2 need their comparison matrices
# audited separately before they can be called paper reproductions.
CASES = {
    "eval3": {
        "folder": "junction", "script": "junction_three_agree.py", "alpha": "7",
        "flows": ["400", "400", "400"], "bus_share": "0.25",
        "seeds": [1, 2, 3, 4, 5], "reference": 7.4159,
        "fixed_input": "fixed_inputs/thesis/eval3/seed-{seed}.jsonl",
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
        "fixed_input": "fixed_inputs/thesis/eval5/seed-{seed}.jsonl",
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
        "fixed_input": "fixed_inputs/thesis/eval7/seed-{seed}.jsonl",
    },
}


def fixed_input_details(
    name, seed, duration, bus_allocation, prefix_duration=None, source_root=ROOT
):
    """Return the committed 600-second input selected for a batch task."""
    pattern = CASES[name].get("fixed_input")
    if pattern is None or bus_allocation != "fixed":
        return None
    if not 0 < duration <= 600:
        raise ValueError("fixed vehicle input duration must be in (0, 600]")
    if prefix_duration is None:
        prefix_duration = duration
    if not 0 < prefix_duration <= duration:
        raise ValueError("fixed vehicle input prefix must be in (0, duration]")
    relative_path = Path(pattern.format(seed=seed))
    path = source_root / relative_path
    schedule = load_fixed_vehicle_input(path, prefix_duration_s=prefix_duration)
    metadata = schedule.metadata
    if metadata.get("case") != name or metadata.get("seed") != seed:
        raise ValueError(f"fixed input metadata mismatch: {relative_path}")
    return {
        "relative_path": relative_path.as_posix(),
        "runtime_path": str(Path("..") / relative_path),
        "schema_version": metadata["schema_version"],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "prefix_duration_s": schedule.prefix_duration_s,
        "prefix_event_count": len(schedule.events),
        "prefix_sha256": schedule.prefix_sha256,
    }


def build_tasks(case_names, seeds_per_case=None, seeds=None):
    """Build tasks from documented seeds, optionally selecting an explicit subset."""
    tasks = []
    for name in case_names:
        documented = CASES[name]["seeds"]
        if seeds is not None:
            unknown = [seed for seed in seeds if seed not in documented]
            if unknown:
                raise ValueError(f"{name} does not document seeds: {unknown}")
            selected = seeds
        else:
            selected = documented[:seeds_per_case]
        tasks.extend((name, seed) for seed in selected)
    return tasks


def source_hashes(source):
    return {
        str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source.rglob("*")
        if (path.is_file() and "statistics" not in path.parts
            and path.suffix in (".py", ".xml", ".sumocfg", ".jsonl"))
    }


def git_metadata():
    """Return reproducibility metadata without making a run depend on Git."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL).strip()
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL).strip())
        return {"commit": commit, "branch": branch or None, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "branch": None, "dirty": None}


def prepare_source(destination, case):
    source = destination / "source"
    source.mkdir()
    for name in ("func", "PathPlanning", "junction", "merge", "fixed_inputs"):
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
    is_three_way = case["folder"] == "junction" and case["script"] == "junction_three_agree.py"
    env = dict(clean_experiment_environment(),
               SUMO_HOME=str(sumo_home),
               PYTHONPATH=str(sumo_home / "tools"),
               MPLBACKEND="Agg", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MCS_TIV_IMPLEMENTATION="thesis",
               MCS_TIV_AUDIT=str(destination / "tiv-audit.json"),
               MCS_EVALUATION_AUDIT=str(destination / "evaluation-metrics.json"),
               MCS_PREDICTION_EVENT_AUDIT=str(destination / "prediction-events.jsonl"))
    if args.diagnostic_traces:
        env.update(
            MCS_VEHICLE_STATE_AUDIT=str(destination / "vehicle-states.jsonl"),
            MCS_CONFLICT_AUDIT=str(destination / "conflicts.jsonl"),
            MCS_NEGOTIATION_AUDIT=str(destination / "negotiations.jsonl"),
            MCS_RUNTIME_AUDIT=str(destination / "runtime.jsonl"),
            MCS_FCD_OUTPUT=str(destination / "fcd.xml.gz"))
    if args.deceleration_active:
        env["MCS_DECELERATION_AUDIT"] = str(destination / "deceleration-audit.json")
    command = [args.python, "-u", case["script"], case["alpha"], str(seed),
               *case["flows"], "--nogui", "--quiet", "--duration", str(args.duration),
               "--bus-allocation", args.bus_allocation]
    fixed_input = fixed_input_details(
        name, seed, args.duration, args.bus_allocation,
        prefix_duration=(args.stop_time if args.stop_time is not None else args.duration),
        source_root=source,
    )
    if fixed_input is not None:
        command += ["--fixed-input", fixed_input["runtime_path"]]
    if args.deceleration_active:
        command.append("--deceleration-active")
    if not is_three_way:
        command += ["--bus-share", case["bus_share"]]
        command.append("--no-save")
    if args.stop_time is not None:
        command += ["--stop-time", str(args.stop_time)]
    manifest = {
        "case": name, "seed": seed, "command": command,
        "input_duration": args.duration, "stop_time": args.stop_time or args.duration,
        "paper_reference_mean_mps": case["reference"],
        "bus_allocation": args.bus_allocation,
        "bus_share": case["bus_share"],
        "fixed_vehicle_input": ({
            "path": fixed_input["relative_path"],
            "schema_version": fixed_input["schema_version"],
            "sha256": fixed_input["sha256"],
            "prefix_duration_s": fixed_input["prefix_duration_s"],
            "prefix_event_count": fixed_input["prefix_event_count"],
            "prefix_sha256": fixed_input["prefix_sha256"],
            "prefix_sha256_scope": "canonical vehicle JSONL records with depart_time_s < prefix_duration_s",
        } if fixed_input is not None else None),
        "decision_method": "deceleration-propagation" if args.deceleration_active else "thesis-tiv",
        "tiv_scoring": dict(TIV_SCORING_MANIFEST),
        "common_instrumentation": {
            "version": "shared-diagnostics-env-clean-v1",
            "decision_controls_cleared": sorted(CONTROLLED_MCS_ENV),
            "priority_hold": {"mode": "off", "enabled": False},
        },
        "diagnostic_traces_requested": args.diagnostic_traces,
        "diagnostic_traces_enabled": bool(args.diagnostic_traces and is_three_way),
        "trace_schema_version": 1 if args.diagnostic_traces and is_three_way else None,
        "source_sha256": initial_hashes,
        "git": git_metadata(),
        "python_version": sys.version,
        "platform": platform.platform(),
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
                    evaluation_metrics_written=(destination / "evaluation-metrics.json").is_file(),
                    prediction_event_audit_written=(destination / "prediction-events.jsonl").is_file(),
                    deceleration_audit_written=(destination / "deceleration-audit.json").is_file(),
                    vehicle_state_audit_written=(destination / "vehicle-states.jsonl").is_file(),
                    conflict_audit_written=(destination / "conflicts.jsonl").is_file(),
                    negotiation_audit_written=(destination / "negotiations.jsonl").is_file(),
                    runtime_audit_written=(destination / "runtime.jsonl").is_file())
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
    parser.add_argument("--seeds", type=int, nargs="+",
                        help="run only these documented seeds for every selected case")
    parser.add_argument("--duration", type=float, default=600,
                        help="scenario duration in seconds (300 for diagnostic comparisons; default: 600)")
    parser.add_argument("--stop-time", type=float,
                        help="smoke test only; retains 600-second input schedule")
    parser.add_argument("--paper", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--bus-allocation", choices=("fixed", "paper-random25"), default="fixed",
                        help="fixed composition for method comparison (default); "
                             "paper-random25 only for original-artifact reproduction")
    parser.add_argument("--deceleration-active", action="store_true",
                        help="use the proposed deceleration-propagation rule")
    parser.add_argument("--diagnostic-traces", action="store_true",
                        help="write Eval.3 replay/conflict/negotiation/runtime JSONL traces")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.seeds_per_case is not None and args.seeds_per_case < 1:
        parser.error("--seeds-per-case must be positive")
    if args.seeds_per_case is not None and args.seeds is not None:
        parser.error("--seeds-per-case and --seeds cannot be combined")
    if not 0 < args.duration <= 600:
        parser.error("--duration must be in (0, 600]")
    if args.stop_time is not None and not 0 < args.stop_time <= args.duration:
        parser.error("--stop-time must be in (0, --duration]")
    if not (args.sumo_home / "bin" / "sumo").is_file() or not (args.sumo_home / "tools" / "traci").is_dir():
        parser.error("--sumo-home must contain bin/sumo and tools/traci")
    if args.paper is not None and not args.paper.is_file():
        parser.error("--paper must name an existing PDF")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        tasks = build_tasks(args.cases, args.seeds_per_case, args.seeds)
    except ValueError as error:
        parser.error(str(error))
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

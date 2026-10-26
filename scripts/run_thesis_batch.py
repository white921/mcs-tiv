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
import datetime
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

# A batch run must not inherit switches or output destinations from an earlier
# experiment. A stale priority-hold setting, for example, would otherwise
# change a baseline whose manifest says that the hold is off.
CONTROLLED_MCS_ENV = {
    "MCS_CHECKPOINT_DIR",
    "MCS_CHECKPOINT_INTERVAL",
    "MCS_CONFLICT_AUDIT",
    "MCS_DECELERATION_AUDIT",
    "MCS_DECELERATION_MODE",
    "MCS_DECELERATION_TIME_HALF_LIFE_S",
    "MCS_EVALUATION_AUDIT",
    "MCS_FCD_OUTPUT",
    "MCS_NEGOTIATION_AUDIT",
    "MCS_PHYSICAL_COLLISION_AUDIT",
    "MCS_PREDICTION_EVENT_AUDIT",
    "MCS_PRIORITY_HOLD_ACTIVATION_SPEED",
    "MCS_PRIORITY_HOLD_MAX_DURATION",
    "MCS_PRIORITY_HOLD_MODE",
    "MCS_PRIORITY_HOLD_PROGRESS_TIMEOUT",
    "MCS_PRIORITY_HOLD_QUEUE_GROWTH_LIMIT",
    "MCS_RUNTIME_AUDIT",
    "MCS_TIV_AUDIT",
    "MCS_TIV_IMPLEMENTATION",
    "MCS_VEHICLE_STATE_AUDIT",
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


def filesystem_component(value):
    """Return a readable, portable component for an experiment directory."""
    component = "".join(
        character if character.isalnum() or character in "+-_." else "-"
        for character in str(value).strip()
    )
    component = re.sub(r"-+", "-", component).strip("-.")
    if not component:
        raise ValueError("run name must contain at least one letter or number")
    return component


def duration_label(duration):
    duration = float(duration)
    return str(int(duration)) if duration.is_integer() else str(duration).replace(".", "p")


def default_run_directory(args, now=None):
    """Choose one canonical directory for one batch invocation."""
    if args.run_name:
        name = filesystem_component(args.run_name)
    else:
        now = now or datetime.datetime.now().astimezone()
        timestamp = now.strftime("%Y%m%dT%H%M%S%z")
        method = "proposal" if args.deceleration_active else "yamashita"
        half_life = getattr(args, "deceleration_time_half_life", 0)
        if args.deceleration_active and half_life > 0:
            method += f"-weighted-{duration_label(half_life)}s"
        if args.conditional_priority_hold:
            method += "-conditional-hold"
        cases = "-".join(args.cases)
        if args.seeds is not None:
            seeds = "seeds-" + "-".join(str(seed) for seed in args.seeds)
        elif args.seeds_per_case is not None:
            seeds = f"first-{args.seeds_per_case}-seeds"
        else:
            seeds = "documented-seeds"
        name = filesystem_component(
            f"{timestamp}__{method}__{cases}__{duration_label(args.duration)}s__{seeds}")
    return ROOT / "results" / "runs" / name


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def clean_experiment_environment(parent=None):
    """Return a copy without state left by an earlier MCS experiment."""
    env = dict(os.environ if parent is None else parent)
    for name in CONTROLLED_MCS_ENV:
        env.pop(name, None)
    return env


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
    supports_replay_checkpoint = name in ("eval3", "eval5", "eval7")
    env = dict(clean_experiment_environment(),
               SUMO_HOME=str(sumo_home),
               PYTHONPATH=str(sumo_home / "tools"),
               MPLBACKEND="Agg", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MCS_TIV_IMPLEMENTATION="thesis",
               MCS_DECELERATION_MODE=("active" if args.deceleration_active else "off"),
               MCS_DECELERATION_TIME_HALF_LIFE_S=str(
                   args.deceleration_time_half_life if args.deceleration_active else 0.0),
               MCS_PRIORITY_HOLD_MODE=(
                   "conditional" if args.conditional_priority_hold else "off"),
               MCS_TIV_AUDIT=str(destination / "tiv-audit.json"),
               MCS_EVALUATION_AUDIT=str(destination / "evaluation-metrics.json"),
               MCS_PHYSICAL_COLLISION_AUDIT=str(
                   destination / "physical-collisions.jsonl"),
               MCS_PREDICTION_EVENT_AUDIT=str(destination / "prediction-events.jsonl"))
    if args.diagnostic_traces:
        env.update(
            MCS_NEGOTIATION_AUDIT=str(destination / "negotiations.jsonl"),
            MCS_FCD_OUTPUT=str(destination / "fcd.xml.gz"),
        )
    if args.diagnostic_traces and supports_replay_checkpoint:
        env.update(
            MCS_VEHICLE_STATE_AUDIT=str(destination / "vehicle-states.jsonl"),
            MCS_CONFLICT_AUDIT=str(destination / "conflicts.jsonl"),
            MCS_RUNTIME_AUDIT=str(destination / "runtime.jsonl"),
        )
    if supports_replay_checkpoint and args.checkpoint_interval > 0:
        env.update(
            MCS_CHECKPOINT_DIR=str(destination / "checkpoints"),
            MCS_CHECKPOINT_INTERVAL=str(args.checkpoint_interval),
        )
    if args.deceleration_active:
        env.update(
            MCS_DECELERATION_AUDIT=str(destination / "deceleration-audit.json"),
        )
    if args.conditional_priority_hold:
        env.update(
            MCS_PRIORITY_HOLD_MODE="conditional",
            MCS_PRIORITY_HOLD_ACTIVATION_SPEED=str(args.priority_hold_activation_speed),
            MCS_PRIORITY_HOLD_PROGRESS_TIMEOUT=str(args.priority_hold_progress_timeout),
            MCS_PRIORITY_HOLD_MAX_DURATION=str(args.priority_hold_max_duration),
            MCS_PRIORITY_HOLD_QUEUE_GROWTH_LIMIT=str(args.priority_hold_queue_growth_limit),
        )
    command = [args.python, "-u", case["script"], case["alpha"], str(seed),
               *case["flows"], "--nogui", "--quiet", "--duration", str(args.duration),
               "--bus-allocation", args.bus_allocation]
    fixed_input = fixed_input_details(
        name, seed, args.duration, args.bus_allocation,
        prefix_duration=args.duration,
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
    if args.resume_checkpoint is not None:
        command += ["--resume-checkpoint", str(args.resume_checkpoint.resolve())]
    manifest = {
        "schema_version": 2,
        "record_type": "simulation-run",
        "experiment_id": args.output.name,
        "simulation_id": f"{name}-seed-{seed}",
        "experiment_directory": str(args.output),
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
        "deceleration_prediction": ({
            "horizon_s": 10.0,
            "time_weighting": ("uniform" if args.deceleration_time_half_life == 0
                               else "exponential-half-life"),
            "time_half_life_s": (args.deceleration_time_half_life or None),
        } if args.deceleration_active else None),
        "priority_hold": ({
            "mode": "conditional-two-stage",
            "key": "priority vehicle + yielding vehicle + 2 m conflict region",
            "activation_speed_mps": args.priority_hold_activation_speed,
            "progress_timeout_s": args.priority_hold_progress_timeout,
            "max_duration_s": args.priority_hold_max_duration,
            "queue_growth_limit": args.priority_hold_queue_growth_limit,
        } if args.conditional_priority_hold else {"mode": "off"}),
        "diagnostic_traces_requested": args.diagnostic_traces,
        "diagnostic_traces_enabled": bool(args.diagnostic_traces),
        "vehicle_state_trace_enabled": bool(args.diagnostic_traces and supports_replay_checkpoint),
        "conflict_trace_enabled": bool(args.diagnostic_traces and supports_replay_checkpoint),
        "negotiation_trace_enabled": bool(args.diagnostic_traces),
        "fcd_trace_enabled": bool(args.diagnostic_traces),
        "trace_schema_version": 2 if args.diagnostic_traces else None,
        "physical_collision_measurement": {
            "source": "SUMO TraCI collision API",
            "events": "physical-collisions.jsonl",
            "summary": "evaluation-metrics.json:physical_safety",
            "controller_conflict_counters_excluded": True,
        },
        "replay_bundle_version": 1 if args.diagnostic_traces and supports_replay_checkpoint else None,
        "checkpointing": ({
            "schema_version": 1,
            "interval_s": args.checkpoint_interval,
            "contains": ["SUMO native state", "MCS controllers and paths",
                         "agreement state", "fixed-input cursor", "random state",
                         "metric accumulators"],
            "resume_from": (str(args.resume_checkpoint.resolve())
                            if args.resume_checkpoint is not None else None),
        } if supports_replay_checkpoint and args.checkpoint_interval > 0 else None),
        "source_sha256": initial_hashes,
        "git": git_metadata(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "sumo_version": subprocess.check_output([str(sumo_home / "bin" / "sumo"), "--version"], text=True),
        "started_epoch": time.time(),
    }
    if args.paper is not None:
        manifest["paper_sha256"] = hashlib.sha256(args.paper.read_bytes()).hexdigest()
    write_json(destination / "manifest.json", manifest)
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
                    physical_collision_audit_written=(
                        destination / "physical-collisions.jsonl").is_file(),
                    prediction_event_audit_written=(destination / "prediction-events.jsonl").is_file(),
                    deceleration_audit_written=(destination / "deceleration-audit.json").is_file(),
                    vehicle_state_audit_written=(destination / "vehicle-states.jsonl").is_file(),
                    conflict_audit_written=(destination / "conflicts.jsonl").is_file(),
                    negotiation_audit_written=(destination / "negotiations.jsonl").is_file(),
                    runtime_audit_written=(destination / "runtime.jsonl").is_file())
    manifest["fcd_written"] = (destination / "fcd.xml.gz").is_file()
    checkpoint_root = destination / "checkpoints"
    manifest["checkpoints_written"] = (
        len([path for path in checkpoint_root.iterdir()
             if path.is_dir() and (path / "checkpoint.json").is_file()])
        if checkpoint_root.is_dir() else 0)
    write_json(destination / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sumo-home", type=Path, required=True)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--output", type=Path,
        help="experiment directory; defaults to a unique directory under results/runs")
    output_group.add_argument(
        "--run-name",
        help="readable experiment directory name created under results/runs")
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
    parser.add_argument(
        "--deceleration-time-half-life", type=float, default=0.0,
        help="exponential future-loss half-life in seconds; 0 keeps uniform 10 s weighting")
    parser.add_argument("--diagnostic-traces", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="write replay/FCD/negotiation diagnostics (default: enabled)")
    parser.add_argument("--conditional-priority-hold", action="store_true",
                        help="remember an agreement, but yield only when the priority vehicle can advance")
    parser.add_argument("--priority-hold-activation-speed", type=float, default=0.5)
    parser.add_argument("--priority-hold-progress-timeout", type=float, default=4.0)
    parser.add_argument("--priority-hold-max-duration", type=float, default=10.0)
    parser.add_argument("--priority-hold-queue-growth-limit", type=int, default=2)
    parser.add_argument("--checkpoint-interval", type=float, default=60.0,
                        help="Eval.3/5/7 paired SUMO/MCS checkpoint interval (default: 60 s)")
    parser.add_argument("--resume-checkpoint", type=Path,
                        help="resume one Eval.3/5/7 task from a paired checkpoint")
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
    if not args.deceleration_time_half_life >= 0:
        parser.error("--deceleration-time-half-life must be non-negative")
    if min(args.deceleration_time_half_life,
           args.priority_hold_activation_speed,
           args.priority_hold_progress_timeout,
           args.priority_hold_max_duration,
           args.priority_hold_queue_growth_limit,
           args.checkpoint_interval) < 0:
        parser.error("prediction and priority-hold limits must be non-negative")
    if args.deceleration_time_half_life > 0 and not args.deceleration_active:
        parser.error("--deceleration-time-half-life requires --deceleration-active")
    if not (args.sumo_home / "bin" / "sumo").is_file() or not (args.sumo_home / "tools" / "traci").is_dir():
        parser.error("--sumo-home must contain bin/sumo and tools/traci")
    if args.paper is not None and not args.paper.is_file():
        parser.error("--paper must name an existing PDF")
    try:
        tasks = build_tasks(args.cases, args.seeds_per_case, args.seeds)
    except ValueError as error:
        parser.error(str(error))
    if args.resume_checkpoint is not None:
        if len(tasks) != 1 or tasks[0][0] not in ("eval3", "eval5", "eval7"):
            parser.error("--resume-checkpoint requires exactly one Eval.3/5/7 task")
        if not (args.resume_checkpoint / "checkpoint.json").is_file():
            parser.error("--resume-checkpoint must name a complete checkpoint directory")
    try:
        args.output = ((args.output.resolve() if args.output is not None
                        else default_run_directory(args).resolve()))
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=False)
    runner_log = args.output / "runner.log"
    started_at = datetime.datetime.now().astimezone()

    def emit(event, **fields):
        record = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "event": event,
            **fields,
        }
        line = json.dumps(record, allow_nan=False)
        with runner_log.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        print(line, flush=True)

    experiment_manifest = {
        "schema_version": 1,
        "record_type": "experiment-run",
        "experiment_id": args.output.name,
        "status": "running",
        "started_at": started_at.isoformat(),
        "started_epoch": started_at.timestamp(),
        "directory": str(args.output),
        "method": "deceleration-propagation" if args.deceleration_active else "yamashita-tiv",
        "deceleration_time_half_life_s": (
            args.deceleration_time_half_life
            if args.deceleration_active and args.deceleration_time_half_life > 0
            else None),
        "conditional_priority_hold": bool(args.conditional_priority_hold),
        "cases": list(args.cases),
        "tasks": [{"case": case, "seed": seed} for case, seed in tasks],
        "duration_s": args.duration,
        "stop_time_s": args.stop_time,
        "workers": args.workers,
        "diagnostic_traces": bool(args.diagnostic_traces),
        "checkpoint_interval_s": args.checkpoint_interval,
        "git": git_metadata(),
    }
    write_json(args.output / "experiment-manifest.json", experiment_manifest)
    emit("experiment_started", tasks=len(tasks), workers=args.workers,
         output=str(args.output))
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
            emit("simulation_finished", **{
                key: report.get(key) for key in (
                    "case", "seed", "exit_code", "elapsed_seconds",
                    "all_speed_mps", "error")})
    reports.sort(key=lambda report: (report["case"], report["seed"]))
    write_json(args.output / "summary.json", reports)
    failures = [report for report in reports if report.get("exit_code") != 0]
    finished_at = datetime.datetime.now().astimezone()
    experiment_manifest.update(
        status="failed" if failures else "completed",
        finished_at=finished_at.isoformat(),
        finished_epoch=finished_at.timestamp(),
        elapsed_seconds=finished_at.timestamp() - started_at.timestamp(),
        completed_simulations=len(reports) - len(failures),
        failed_simulations=len(failures),
        summary_file="summary.json",
        runner_log="runner.log",
    )
    write_json(args.output / "experiment-manifest.json", experiment_manifest)
    emit("experiment_finished", status=experiment_manifest["status"],
         completed=experiment_manifest["completed_simulations"],
         failed=experiment_manifest["failed_simulations"])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

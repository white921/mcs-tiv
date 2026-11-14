#!/usr/bin/env python3
"""Run three Eval.7 methods through one ordered, work-conserving slot queue.

Each method uses its own clean Git worktree and writes one normal thesis-batch
experiment directory.  Tasks are queued in integrated, UTF, Yamashita order;
the initial 15 slots therefore contain ten integrated and five UTF runs.
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import threading
import time
from types import SimpleNamespace


METHOD_ORDER = ("integrated", "utf", "yamashita")
EXPECTED_PYTHON = (3, 15, 1)
EXPECTED_SUMO = "1.28.0"


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def append_jsonl(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, allow_nan=False) + "\n")


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runner(root, label):
    path = root / "scripts" / "run_thesis_batch.py"
    spec = importlib.util.spec_from_file_location(
        f"run_thesis_batch_{label}", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_ordered_tasks(seeds):
    return [
        (method, seed)
        for method in METHOD_ORDER
        for seed in seeds
    ]


def count_sumo_processes():
    result = subprocess.run(
        ["pgrep", "-x", "sumo"], text=True, capture_output=True, check=False
    )
    if result.returncode == 1:
        return 0
    if result.returncode != 0:
        raise RuntimeError(f"pgrep failed: {result.stderr.strip()}")
    return len([line for line in result.stdout.splitlines() if line.strip()])


def python_version(python):
    output = subprocess.check_output(
        [python, "-c", "import platform; print(platform.python_version())"],
        text=True,
    ).strip()
    return tuple(int(part) for part in output.split(".")), output


def sumo_version_matches(output, expected=EXPECTED_SUMO):
    first_line = output.splitlines()[0] if output.splitlines() else ""
    return bool(re.search(rf"\b{re.escape(expected)}\b", first_line))


def base_method_args(args, runner, output, method):
    return SimpleNamespace(
        output=output,
        sumo_home=args.sumo_home,
        decision_method=("utf" if method == "utf" else "tivtep"),
        deceleration_active=(method == "integrated"),
        deceleration_convex_lambda=runner.DEFAULT_CONVEX_LAMBDA,
        agreement_lease_seconds=0.0,
        merge_negotiation_lead_seconds=0.0,
        two_stage_merge_negotiation=False,
        diagnostic_traces=True,
        checkpoint_interval=60.0,
        python=str(args.python),
        duration=args.duration,
        bus_allocation="fixed",
        fixed_input_override=None,
        eval7_flows=list(args.eval7_flows),
        stop_time=args.stop_time,
        resume_checkpoint=None,
        paper=None,
        run_git_metadata=runner.git_metadata(),
    )


def method_manifest(args, method, method_args, tasks, started_at):
    return {
        "schema_version": 1,
        "record_type": "experiment-run",
        "experiment_id": method_args.output.name,
        "status": "running",
        "started_at": started_at.isoformat(),
        "started_epoch": started_at.timestamp(),
        "directory": str(method_args.output),
        "method": {
            "integrated": "normalized-deceleration-propagation",
            "utf": "utf",
            "yamashita": "yamashita-tivtep",
        }[method],
        "requested_decision_method": method_args.decision_method,
        "deceleration_convex_lambda": (
            method_args.deceleration_convex_lambda
            if method == "integrated" else None),
        "cases": ["eval7"],
        "eval7_flows_vph": {
            "requesting": args.eval7_flows[0],
            "accepting": args.eval7_flows[1],
        },
        "tasks": [{"case": "eval7", "seed": seed} for seed in tasks],
        "duration_s": args.duration,
        "stop_time_s": args.stop_time,
        "workers": args.slots,
        "scheduler": {
            "type": "shared-ordered-work-conserving-queue",
            "slots": args.slots,
            "method_order": list(METHOD_ORDER),
            "initial_launch": {"integrated": 10, "utf": 5, "yamashita": 0},
            "machine_wide_limit": args.slots,
            "orchestration_log": "orchestration.jsonl",
        },
        "diagnostic_traces": True,
        "checkpoint_interval_s": 60.0,
        "git": method_args.run_git_metadata,
    }


def validate_preflight(args, contexts):
    versions, version_text = python_version(str(args.python))
    if versions != EXPECTED_PYTHON:
        raise RuntimeError(
            f"Python must be 3.15.1, got {version_text} from {args.python}"
        )
    sumo_output = subprocess.check_output(
        [str(args.sumo_home / "bin" / "sumo"), "--version"], text=True
    )
    if not sumo_version_matches(sumo_output):
        raise RuntimeError(f"SUMO must be {EXPECTED_SUMO}: {sumo_output.splitlines()[0]}")
    existing_sumo = count_sumo_processes()
    if existing_sumo:
        raise RuntimeError(
            f"refusing to start with {existing_sumo} existing SUMO process(es)"
        )

    commits = set()
    runner_hashes = set()
    orchestrator_hashes = set()
    input_hashes = {seed: set() for seed in args.seeds}
    for method, context in contexts.items():
        metadata = context["args"].run_git_metadata
        if metadata["commit"] is None or metadata["dirty"] is not False:
            raise RuntimeError(f"{method} worktree is not a clean Git commit: {metadata}")
        commits.add(metadata["commit"])
        root = context["root"]
        runner_hashes.add(file_sha256(root / "scripts" / "run_thesis_batch.py"))
        orchestrator_hashes.add(
            file_sha256(root / "scripts" / "run_thesis_shared_queue.py")
        )
        runner = context["runner"]
        built = runner.build_tasks(
            ["eval7"], seeds=args.seeds, eval7_flows=args.eval7_flows
        )
        if built != [("eval7", seed) for seed in args.seeds]:
            raise RuntimeError(f"unexpected task selection in {method}: {built}")
        for seed in args.seeds:
            details = runner.fixed_input_details(
                "eval7",
                seed,
                args.duration,
                "fixed",
                prefix_duration=args.duration,
                source_root=root,
                flows=args.eval7_flows,
            )
            input_hashes[seed].add(details["sha256"])
    if len(commits) != 1:
        raise RuntimeError(f"worktrees do not share one source commit: {sorted(commits)}")
    if len(runner_hashes) != 1 or len(orchestrator_hashes) != 1:
        raise RuntimeError("runner/orchestrator source differs between worktrees")
    mismatched = [seed for seed, hashes in input_hashes.items() if len(hashes) != 1]
    if mismatched:
        raise RuntimeError(f"fixed input hashes differ between methods: {mismatched}")
    return {
        "source_commit": next(iter(commits)),
        "python_version": version_text,
        "sumo_version": EXPECTED_SUMO,
        "existing_sumo_processes": existing_sumo,
        "fixed_input_sha256": {
            str(seed): next(iter(hashes)) for seed, hashes in input_hashes.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for method in METHOD_ORDER:
        parser.add_argument(f"--{method}-root", type=Path, required=True)
        parser.add_argument(f"--{method}-run-name", required=True)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument(
        "--eval7-flows", type=int, nargs=2, required=True,
        metavar=("REQUESTING", "ACCEPTING"),
    )
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--stop-time", type=float)
    parser.add_argument("--slots", type=int, default=15)
    args = parser.parse_args()

    if args.slots != 15:
        parser.error("this formal scheduler requires exactly 15 slots")
    if len(args.seeds) != 10 or len(set(args.seeds)) != 10:
        parser.error("--seeds must contain exactly 10 unique values")
    if not 0 < args.duration <= 600:
        parser.error("--duration must be in (0, 600]")
    if args.stop_time is not None and not 0 < args.stop_time <= args.duration:
        parser.error("--stop-time must be in (0, --duration]")
    if any(flow < 0 or flow > 1800 for flow in args.eval7_flows):
        parser.error("--eval7-flows values must be between 0 and 1800")
    if len(set(METHOD_ORDER)) != len(METHOD_ORDER):
        raise RuntimeError("method order is not unique")

    contexts = {}
    outputs = []
    for method in METHOD_ORDER:
        root = getattr(args, f"{method}_root").resolve()
        if not root.is_dir():
            parser.error(f"--{method}-root does not exist: {root}")
        output = root / "results" / "runs" / getattr(args, f"{method}_run_name")
        if output.exists():
            parser.error(f"output already exists: {output}")
        runner = load_runner(root, method)
        method_args = base_method_args(args, runner, output, method)
        contexts[method] = {
            "root": root,
            "runner": runner,
            "args": method_args,
            "manifest": None,
            "reports": [],
            "finalized": False,
        }
        outputs.append(output)

    preflight = validate_preflight(args, contexts)
    started_at = datetime.datetime.now().astimezone()
    for method, context in contexts.items():
        output = context["args"].output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=False, exist_ok=False)
        manifest = method_manifest(
            args, method, context["args"], args.seeds, started_at
        )
        manifest["preflight"] = preflight
        context["manifest"] = manifest
        write_json(output / "experiment-manifest.json", manifest)
        append_jsonl(output / "runner.log", {
            "time": started_at.isoformat(),
            "event": "experiment_started",
            "method": method,
            "tasks": len(args.seeds),
            "shared_slots": args.slots,
        })

    emit_lock = threading.Lock()

    def emit(event, **fields):
        record = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "event": event,
            **fields,
        }
        with emit_lock:
            for output in outputs:
                append_jsonl(output / "orchestration.jsonl", record)
            print(json.dumps(record, allow_nan=False), flush=True)
        return record

    def emit_method(method, event, **fields):
        record = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "event": event,
            "method": method,
            **fields,
        }
        with emit_lock:
            append_jsonl(contexts[method]["args"].output / "runner.log", record)
        return record

    queue = build_ordered_tasks(args.seeds)
    active = 0
    max_active = 0
    active_lock = threading.Lock()
    stop_monitor = threading.Event()
    monitor_state = {"max_sumo": 0, "violation": None}

    def monitor_sumo():
        previous = None
        while not stop_monitor.wait(0.25):
            try:
                count = count_sumo_processes()
            except Exception as error:
                monitor_state["violation"] = repr(error)
                emit("sumo_monitor_error", error=repr(error))
                return
            monitor_state["max_sumo"] = max(monitor_state["max_sumo"], count)
            if count != previous:
                emit("machine_sumo_count", count=count)
                previous = count
            if count > args.slots:
                monitor_state["violation"] = (
                    f"machine-wide SUMO count {count} exceeded {args.slots}"
                )
                emit("machine_slot_limit_exceeded", count=count, limit=args.slots)
                return

    monitor_thread = threading.Thread(target=monitor_sumo, daemon=True)
    monitor_thread.start()

    def execute(method, seed, queue_index):
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
            active_now = active
        started = time.monotonic()
        emit(
            "simulation_started", method=method, seed=seed,
            queue_index=queue_index, active_runs=active_now,
        )
        emit_method(method, "simulation_started", seed=seed, queue_index=queue_index)
        try:
            report = contexts[method]["runner"].run_task(
                ("eval7", seed), contexts[method]["args"]
            )
        except Exception as error:
            report = {"case": "eval7", "seed": seed, "error": repr(error)}
        finished = time.monotonic()
        with active_lock:
            active -= 1
            active_now = active
        emit(
            "simulation_finished", method=method, seed=seed,
            queue_index=queue_index, active_runs=active_now,
            exit_code=report.get("exit_code"), error=report.get("error"),
            elapsed_seconds=finished - started,
        )
        emit_method(
            method, "simulation_finished", seed=seed,
            exit_code=report.get("exit_code"), error=report.get("error"),
            elapsed_seconds=finished - started,
        )
        return method, seed, queue_index, report, finished

    def report_failed(report):
        return (
            report.get("exit_code") != 0 or
            report.get("source_unchanged") is not True
        )

    def finalize_method(method, forced_status=None):
        context = contexts[method]
        if context["finalized"]:
            return
        reports = sorted(context["reports"], key=lambda value: value["seed"])
        expected_count = len(args.seeds)
        failures = [report for report in reports if report_failed(report)]
        if forced_status is not None:
            status = forced_status
        elif len(reports) < expected_count:
            status = "incomplete"
        else:
            status = "failed" if failures else "completed"
        finished_at = datetime.datetime.now().astimezone()
        write_json(context["args"].output / "summary.json", reports)
        context["manifest"].update(
            status=status,
            finished_at=finished_at.isoformat(),
            finished_epoch=finished_at.timestamp(),
            elapsed_seconds=finished_at.timestamp() - started_at.timestamp(),
            completed_simulations=len(reports) - len(failures),
            failed_simulations=len(failures),
            missing_simulations=expected_count - len(reports),
            summary_file="summary.json",
            runner_log="runner.log",
            max_shared_active_runs=max_active,
            max_machine_sumo_processes=monitor_state["max_sumo"],
            machine_slot_violation=monitor_state["violation"],
        )
        write_json(
            context["args"].output / "experiment-manifest.json",
            context["manifest"],
        )
        emit_method(
            method, "experiment_finished", status=status,
            completed=context["manifest"]["completed_simulations"],
            failed=context["manifest"]["failed_simulations"],
            missing=context["manifest"]["missing_simulations"],
        )
        emit(
            "method_finished", method=method, status=status,
            completed=context["manifest"]["completed_simulations"],
            failed=context["manifest"]["failed_simulations"],
            missing=context["manifest"]["missing_simulations"],
        )
        context["finalized"] = True

    emit(
        "orchestration_started", source_commit=preflight["source_commit"],
        queue=[{"method": method, "seed": seed} for method, seed in queue],
        slots=args.slots,
    )
    abort = False
    next_index = 0
    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.slots) as pool:
        while next_index < min(args.slots, len(queue)):
            method, seed = queue[next_index]
            future = pool.submit(execute, method, seed, next_index)
            futures[future] = (method, seed, next_index)
            next_index += 1
        emit(
            "initial_slots_submitted", submitted=next_index,
            methods={
                method: sum(1 for queued_method, _ in queue[:next_index]
                            if queued_method == method)
                for method in METHOD_ORDER
            },
        )

        while futures:
            done, _ = concurrent.futures.wait(
                futures, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                futures.pop(future)
                method, seed, queue_index, report, finished = future.result()
                contexts[method]["reports"].append(report)
                if report_failed(report):
                    abort = True
                    emit(
                        "orchestration_abort_requested", method=method, seed=seed,
                        exit_code=report.get("exit_code"),
                        source_unchanged=report.get("source_unchanged"),
                        error=report.get("error"),
                    )
                if len(contexts[method]["reports"]) == len(args.seeds):
                    finalize_method(method)
                if (not abort and monitor_state["violation"] is None and
                        next_index < len(queue)):
                    next_method, next_seed = queue[next_index]
                    submitted = time.monotonic()
                    replacement = pool.submit(
                        execute, next_method, next_seed, next_index
                    )
                    futures[replacement] = (next_method, next_seed, next_index)
                    emit(
                        "slot_refilled", after_method=method, after_seed=seed,
                        next_method=next_method, next_seed=next_seed,
                        next_queue_index=next_index,
                        refill_delay_seconds=max(0.0, submitted - finished),
                    )
                    next_index += 1

    stop_monitor.set()
    monitor_thread.join(timeout=2)
    if monitor_state["violation"] is not None:
        abort = True
    for method in METHOD_ORDER:
        if not contexts[method]["finalized"]:
            finalize_method(method)
    statuses = {
        method: contexts[method]["manifest"]["status"]
        for method in METHOD_ORDER
    }
    emit(
        "orchestration_finished", statuses=statuses,
        submitted_tasks=next_index, max_active_runs=max_active,
        max_machine_sumo_processes=monitor_state["max_sumo"],
        machine_slot_violation=monitor_state["violation"],
    )
    success = (
        not abort and next_index == len(queue) and
        all(status == "completed" for status in statuses.values()) and
        max_active <= args.slots and
        monitor_state["max_sumo"] <= args.slots
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

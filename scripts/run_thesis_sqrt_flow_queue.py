#!/usr/bin/env python3
"""Run the Eval.7 sqrt-followers traffic-flow sweep in one 15-slot queue.

Each traffic flow writes one normal thesis experiment directory in its own
clean Git worktree.  The queue is ordered 300, 500, 700, then 1000 veh/h on
the requesting side, so the initial 15 slots contain all ten 300-flow runs
and the five 500-flow holdout runs.  Finished slots are filled immediately
from the five additional 500-flow development runs, then the 700- and
1000-flow tasks.
"""

from __future__ import annotations

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


FLOW_ORDER = (300, 500, 700, 1000)
FLOW_SEEDS = {
    300: tuple(range(33, 43)),
    500: (43, 44, 45, 46, 47, 6, 8, 9, 10, 12),
    700: tuple(range(33, 43)),
    1000: tuple(range(33, 43)),
}
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


def load_runner(root, flow):
    path = root / "scripts" / "run_thesis_batch.py"
    spec = importlib.util.spec_from_file_location(
        f"run_thesis_batch_flow_{flow}", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_ordered_tasks():
    return [
        (flow, seed)
        for flow in FLOW_ORDER
        for seed in FLOW_SEEDS[flow]
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


def flow_args(args, runner, root, flow):
    return SimpleNamespace(
        output=root / "results" / "runs" / args.run_name_template.format(flow=flow),
        sumo_home=args.sumo_home,
        decision_method="tivtep",
        deceleration_active=True,
        deceleration_time_half_life=0.0,
        deceleration_loss_lambda=2.0,
        deceleration_loss_normalization="sqrt-followers",
        deceleration_negative_loss_credit_weight=0.0,
        rejection_wait_cap=0.0,
        agreement_lease_seconds=0.0,
        merge_negotiation_lead_seconds=0.0,
        two_stage_merge_negotiation=False,
        deceleration_loss_mode="integrated",
        diagnostic_traces=True,
        checkpoint_interval=60.0,
        python=str(args.python),
        duration=600.0,
        bus_allocation="fixed",
        fixed_input_override=None,
        eval7_flows=[flow, 1000],
        stop_time=None,
        resume_checkpoint=None,
        paper=None,
        run_git_metadata=runner.git_metadata(),
    )


def experiment_manifest(args, flow, flow_args_value, started_at):
    seeds = FLOW_SEEDS[flow]
    return {
        "schema_version": 1,
        "record_type": "experiment-run",
        "experiment_id": flow_args_value.output.name,
        "status": "running",
        "started_at": started_at.isoformat(),
        "started_epoch": started_at.timestamp(),
        "directory": str(flow_args_value.output),
        "method": "deceleration-propagation",
        "requested_decision_method": "tivtep",
        "deceleration_time_half_life_s": None,
        "deceleration_loss_lambda": 2.0,
        "deceleration_loss_normalization": "sqrt-followers",
        "deceleration_negative_loss_credit_weight": 0.0,
        "rejection_wait_cap_s": 0.0,
        "cases": ["eval7"],
        "eval7_flows_vph": {"requesting": flow, "accepting": 1000},
        "tasks": [{"case": "eval7", "seed": seed} for seed in seeds],
        "duration_s": 600.0,
        "workers": args.slots,
        "scheduler": {
            "type": "shared-flow-work-conserving-queue",
            "slots": args.slots,
            "flow_order": list(FLOW_ORDER),
            "initial_launch": {"300": 10, "500": 5, "700": 0, "1000": 0},
            "machine_wide_limit": args.slots,
            "orchestration_log": "orchestration.jsonl",
        },
        "diagnostic_traces": True,
        "checkpoint_interval_s": 60.0,
        "git": flow_args_value.run_git_metadata,
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
    input_hashes = {}
    for flow, context in contexts.items():
        metadata = context["args"].run_git_metadata
        if metadata["commit"] is None or metadata["dirty"] is not False:
            raise RuntimeError(f"flow {flow} worktree is not clean: {metadata}")
        commits.add(metadata["commit"])
        root = context["root"]
        runner_hashes.add(file_sha256(root / "scripts" / "run_thesis_batch.py"))
        orchestrator_hashes.add(
            file_sha256(root / "scripts" / "run_thesis_sqrt_flow_queue.py")
        )
        runner = context["runner"]
        seeds = FLOW_SEEDS[flow]
        built = runner.build_tasks(
            ["eval7"], seeds=seeds, eval7_flows=[flow, 1000]
        )
        if built != [("eval7", seed) for seed in seeds]:
            raise RuntimeError(f"unexpected task selection for flow {flow}: {built}")
        for seed in seeds:
            details = runner.fixed_input_details(
                "eval7",
                seed,
                600.0,
                "fixed",
                prefix_duration=600.0,
                source_root=root,
                flows=[flow, 1000],
            )
            input_hashes[f"{flow}:{seed}"] = details["sha256"]
    if len(commits) != 1:
        raise RuntimeError(f"worktrees do not share one source commit: {sorted(commits)}")
    if len(runner_hashes) != 1 or len(orchestrator_hashes) != 1:
        raise RuntimeError("runner/orchestrator source differs between worktrees")
    return {
        "source_commit": next(iter(commits)),
        "python_version": version_text,
        "sumo_version": EXPECTED_SUMO,
        "existing_sumo_processes": existing_sumo,
        "fixed_input_sha256": input_hashes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flow in FLOW_ORDER:
        parser.add_argument(f"--flow-{flow}-root", type=Path, required=True)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--slots", type=int, default=15)
    parser.add_argument(
        "--run-name-template",
        default="eval7-{flow}-1000-integrated-lambda2-sqrt-followers-600s-development-20261111",
    )
    args = parser.parse_args()
    if args.slots != 15:
        parser.error("this formal scheduler requires exactly 15 slots")
    if "{flow}" not in args.run_name_template:
        parser.error("--run-name-template must contain {flow}")

    contexts = {}
    outputs = []
    for flow in FLOW_ORDER:
        root = getattr(args, f"flow_{flow}_root").resolve()
        if not root.is_dir():
            parser.error(f"flow {flow} root does not exist: {root}")
        runner = load_runner(root, flow)
        run_args = flow_args(args, runner, root, flow)
        if run_args.output.exists():
            parser.error(f"output already exists: {run_args.output}")
        contexts[flow] = {
            "root": root,
            "runner": runner,
            "args": run_args,
            "manifest": None,
            "reports": [],
            "finalized": False,
        }
        outputs.append(run_args.output)

    preflight = validate_preflight(args, contexts)
    started_at = datetime.datetime.now().astimezone()
    for flow, context in contexts.items():
        output = context["args"].output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=False, exist_ok=False)
        manifest = experiment_manifest(args, flow, context["args"], started_at)
        manifest["preflight"] = preflight
        context["manifest"] = manifest
        write_json(output / "experiment-manifest.json", manifest)
        append_jsonl(output / "runner.log", {
            "time": started_at.isoformat(),
            "event": "experiment_started",
            "flow": flow,
            "tasks": len(FLOW_SEEDS[flow]),
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

    def emit_flow(flow, event, **fields):
        record = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "event": event,
            "flow": flow,
            **fields,
        }
        with emit_lock:
            append_jsonl(contexts[flow]["args"].output / "runner.log", record)

    queue = build_ordered_tasks()
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

    def execute(flow, seed, queue_index):
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
            active_now = active
        started = time.monotonic()
        emit(
            "simulation_started", flow=flow, seed=seed,
            queue_index=queue_index, active_runs=active_now,
        )
        emit_flow(flow, "simulation_started", seed=seed, queue_index=queue_index)
        try:
            report = contexts[flow]["runner"].run_task(
                ("eval7", seed), contexts[flow]["args"]
            )
        except Exception as error:
            report = {"case": "eval7", "seed": seed, "error": repr(error)}
        finished = time.monotonic()
        with active_lock:
            active -= 1
            active_now = active
        emit(
            "simulation_finished", flow=flow, seed=seed,
            queue_index=queue_index, active_runs=active_now,
            exit_code=report.get("exit_code"), error=report.get("error"),
            elapsed_seconds=finished - started,
        )
        emit_flow(
            flow, "simulation_finished", seed=seed,
            exit_code=report.get("exit_code"), error=report.get("error"),
            elapsed_seconds=finished - started,
        )
        return flow, seed, queue_index, report, finished

    def report_failed(report):
        return (
            report.get("exit_code") != 0 or
            report.get("source_unchanged") is not True
        )

    def finalize_flow(flow, forced_status=None):
        context = contexts[flow]
        if context["finalized"]:
            return
        reports = sorted(context["reports"], key=lambda value: value["seed"])
        expected_count = len(FLOW_SEEDS[flow])
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
        write_json(context["args"].output / "experiment-manifest.json", context["manifest"])
        emit_flow(
            flow, "experiment_finished", status=status,
            completed=context["manifest"]["completed_simulations"],
            failed=context["manifest"]["failed_simulations"],
            missing=context["manifest"]["missing_simulations"],
        )
        emit(
            "flow_finished", flow=flow, status=status,
            completed=context["manifest"]["completed_simulations"],
            failed=context["manifest"]["failed_simulations"],
            missing=context["manifest"]["missing_simulations"],
        )
        context["finalized"] = True

    emit(
        "orchestration_started", source_commit=preflight["source_commit"],
        queue=[{"flow": flow, "seed": seed} for flow, seed in queue],
        slots=args.slots,
    )
    abort = False
    next_index = 0
    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.slots) as pool:
        while next_index < min(args.slots, len(queue)):
            flow, seed = queue[next_index]
            future = pool.submit(execute, flow, seed, next_index)
            futures[future] = (flow, seed, next_index)
            next_index += 1
        emit(
            "initial_slots_submitted", submitted=next_index,
            flows={
                str(flow): sum(1 for queued_flow, _ in queue[:next_index]
                               if queued_flow == flow)
                for flow in FLOW_ORDER
            },
        )

        while futures:
            done, _ = concurrent.futures.wait(
                futures, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                futures.pop(future)
                flow, seed, queue_index, report, finished = future.result()
                contexts[flow]["reports"].append(report)
                if report_failed(report):
                    abort = True
                    emit(
                        "orchestration_abort_requested", flow=flow, seed=seed,
                        exit_code=report.get("exit_code"),
                        source_unchanged=report.get("source_unchanged"),
                        error=report.get("error"),
                    )
                if len(contexts[flow]["reports"]) == len(FLOW_SEEDS[flow]):
                    finalize_flow(flow)
                if (not abort and monitor_state["violation"] is None and
                        next_index < len(queue)):
                    next_flow, next_seed = queue[next_index]
                    submitted = time.monotonic()
                    replacement = pool.submit(
                        execute, next_flow, next_seed, next_index
                    )
                    futures[replacement] = (next_flow, next_seed, next_index)
                    emit(
                        "slot_refilled", after_flow=flow, after_seed=seed,
                        next_flow=next_flow, next_seed=next_seed,
                        next_queue_index=next_index,
                        refill_delay_seconds=max(0.0, submitted - finished),
                    )
                    next_index += 1

    stop_monitor.set()
    monitor_thread.join(timeout=2)
    if monitor_state["violation"] is not None:
        abort = True
    for flow in FLOW_ORDER:
        if not contexts[flow]["finalized"]:
            finalize_flow(flow)
    statuses = {
        str(flow): contexts[flow]["manifest"]["status"] for flow in FLOW_ORDER
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

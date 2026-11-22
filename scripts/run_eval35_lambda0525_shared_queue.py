#!/usr/bin/env python3
"""Run the formal Eval.3/5 lambda=0.525 comparison in one 15-slot queue."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from types import SimpleNamespace


EXPECTED_PYTHON = (3, 15, 1)
EXPECTED_SUMO = "1.28.0"
LAMBDA = 0.525
METHOD_ORDER = ("yamashita", "proposal")
CONDITION_ORDER = ("eval3-400", "eval3-500", "eval5-300")
CONTEXT_SPECS = {
    "eval3-400-yamashita": {
        "eval": "eval3", "case": "eval3", "flows": (400, 400, 400),
        "method": "yamashita", "condition": "eval3-400",
    },
    "eval3-400-proposal": {
        "eval": "eval3", "case": "eval3", "flows": (400, 400, 400),
        "method": "proposal", "condition": "eval3-400",
    },
    "eval3-500-yamashita": {
        "eval": "eval3", "case": "eval3", "flows": (500, 500, 500),
        "method": "yamashita", "condition": "eval3-500",
    },
    "eval3-500-proposal": {
        "eval": "eval3", "case": "eval3", "flows": (500, 500, 500),
        "method": "proposal", "condition": "eval3-500",
    },
    "eval5-300-yamashita": {
        "eval": "eval5", "case": "eval5", "flows": (300, 300, 300, 300),
        "method": "yamashita", "condition": "eval5-300",
    },
    "eval5-300-proposal": {
        "eval": "eval5", "case": "eval5", "flows": (300, 300, 300, 300),
        "method": "proposal", "condition": "eval5-300",
    },
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def append_jsonl(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, allow_nan=False) + "\n")


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runner(root, tag):
    path = root / "scripts" / "run_thesis_batch.py"
    spec = importlib.util.spec_from_file_location(f"eval35_runner_{tag}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def count_sumo_processes():
    result = subprocess.run(
        ["pgrep", "-x", "sumo"], text=True, capture_output=True, check=False
    )
    if result.returncode == 1:
        return 0
    if result.returncode != 0:
        raise RuntimeError(f"pgrep failed: {result.stderr.strip()}")
    return len([line for line in result.stdout.splitlines() if line.strip()])


def sumo_version_matches(output, expected=EXPECTED_SUMO):
    first_line = output.splitlines()[0] if output.splitlines() else ""
    return bool(re.search(rf"\b{re.escape(expected)}\b", first_line))


def build_ordered_tasks(seeds):
    tasks = []
    for condition in CONDITION_ORDER:
        for seed in seeds:
            for method in METHOD_ORDER:
                tasks.append((f"{condition}-{method}", seed))
    return tasks


def fixed_input_template(spec):
    return (
        "fixed_inputs/thesis/eval35-paper-comparison/"
        f"{spec['condition']}/seed-{{seed}}.jsonl"
    )


def method_args(args, runner, output, spec):
    proposal = spec["method"] == "proposal"
    return SimpleNamespace(
        output=output,
        sumo_home=args.sumo_home,
        decision_method="tivtep",
        deceleration_active=proposal,
        deceleration_convex_lambda=LAMBDA,
        agreement_lease_seconds=0.0,
        merge_negotiation_lead_seconds=0.0,
        two_stage_merge_negotiation=False,
        diagnostic_traces=True,
        checkpoint_interval=60.0,
        python=str(args.python),
        duration=600.0,
        bus_allocation="fixed",
        fixed_input_override=fixed_input_template(spec),
        case_flows=list(spec["flows"]),
        eval7_flows=None,
        stop_time=None,
        resume_checkpoint=None,
        paper=None,
        run_git_metadata=runner.git_metadata(),
    )


def context_manifest(args, context, started_at):
    spec = context["spec"]
    return {
        "schema_version": 1,
        "record_type": "experiment-run",
        "experiment_id": context["args"].output.name,
        "status": "running",
        "started_at": started_at.isoformat(),
        "started_epoch": started_at.timestamp(),
        "directory": str(context["args"].output),
        "formal_classification": "formal",
        "eval": spec["eval"],
        "condition": spec["condition"],
        "case": spec["case"],
        "flows_vph": list(spec["flows"]),
        "method": (
            "normalized-deceleration-propagation"
            if spec["method"] == "proposal" else "yamashita-tivtep"
        ),
        "requested_decision_method": "tivtep",
        "deceleration_convex_lambda": LAMBDA if spec["method"] == "proposal" else None,
        "tasks": [{"case": spec["case"], "seed": seed} for seed in args.seeds],
        "duration_s": 600.0,
        "bus_share": 0.25,
        "workers": args.slots,
        "scheduler": {
            "type": "eval35-ordered-work-conserving-shared-queue",
            "slots": args.slots,
            "condition_order": list(CONDITION_ORDER),
            "method_order_within_seed": list(METHOD_ORDER),
            "machine_wide_limit": args.slots,
            "orchestration_log": "orchestration.jsonl",
            "postprocess_after_eval": True,
        },
        "diagnostic_traces": True,
        "checkpoint_interval_s": 60.0,
        "git": context["args"].run_git_metadata,
    }


def validate_preflight(args, contexts):
    version_text = subprocess.check_output(
        [str(args.python), "-c", "import platform; print(platform.python_version())"],
        text=True,
    ).strip()
    if tuple(int(part) for part in version_text.split(".")) != EXPECTED_PYTHON:
        raise RuntimeError(f"Python must be 3.15.1, got {version_text}")
    sumo_output = subprocess.check_output(
        [str(args.sumo_home / "bin" / "sumo"), "--version"], text=True
    )
    if not sumo_version_matches(sumo_output):
        raise RuntimeError(f"SUMO must be {EXPECTED_SUMO}: {sumo_output.splitlines()[0]}")
    existing_sumo = count_sumo_processes()
    if existing_sumo:
        raise RuntimeError(f"refusing to start with {existing_sumo} existing SUMO process(es)")

    commits = set()
    runner_hashes = set()
    scheduler_hashes = set()
    input_hashes = {}
    for tag, context in contexts.items():
        metadata = context["args"].run_git_metadata
        if metadata["commit"] is None or metadata["dirty"] is not False:
            raise RuntimeError(f"{tag} worktree is not a clean Git commit: {metadata}")
        commits.add(metadata["commit"])
        root = context["root"]
        runner_hashes.add(file_sha256(root / "scripts" / "run_thesis_batch.py"))
        scheduler_hashes.add(file_sha256(root / "scripts" / Path(__file__).name))
        spec = context["spec"]
        for seed in args.seeds:
            details = context["runner"].fixed_input_details(
                spec["case"], seed, 600, "fixed",
                prefix_duration=600, source_root=root, flows=spec["flows"],
                relative_path_override=fixed_input_template(spec),
            )
            input_hashes.setdefault((spec["condition"], seed), set()).add(details["sha256"])
    if len(commits) != 1:
        raise RuntimeError(f"worktrees do not share one source commit: {sorted(commits)}")
    if len(runner_hashes) != 1 or len(scheduler_hashes) != 1:
        raise RuntimeError("runner or scheduler source differs between worktrees")
    mismatched = [key for key, hashes in input_hashes.items() if len(hashes) != 1]
    if mismatched:
        raise RuntimeError(f"fixed input hashes differ between methods: {mismatched}")
    return {
        "source_commit": next(iter(commits)),
        "python_version": version_text,
        "sumo_version": EXPECTED_SUMO,
        "existing_sumo_processes": existing_sumo,
        "fixed_input_sha256": {
            f"{condition}/seed-{seed}": next(iter(hashes))
            for (condition, seed), hashes in input_hashes.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--context", action="append", nargs=4, required=True,
        metavar=("TAG", "ROOT", "RUN_NAME", "RESULT_BRANCH"),
    )
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(13, 23)))
    parser.add_argument("--slots", type=int, default=15)
    parser.add_argument("--cleanup-workers", type=int, default=2)
    parser.add_argument("--push-results", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    if args.slots != 15:
        parser.error("this formal scheduler requires exactly 15 slots")
    if tuple(args.seeds) != tuple(range(13, 23)):
        parser.error("formal seeds must be exactly 13 through 22 in order")

    supplied = {}
    for tag, root_text, run_name, branch in args.context:
        if tag in supplied:
            parser.error(f"duplicate context: {tag}")
        supplied[tag] = (Path(root_text).resolve(), run_name, branch)
    if set(supplied) != set(CONTEXT_SPECS):
        parser.error(
            "--context tags must be exactly: " + ", ".join(CONTEXT_SPECS)
        )

    contexts = {}
    outputs = []
    for tag, spec in CONTEXT_SPECS.items():
        root, run_name, branch = supplied[tag]
        if not root.is_dir():
            parser.error(f"context root does not exist: {root}")
        output = root / "results" / "runs" / run_name
        if output.exists():
            parser.error(f"output already exists: {output}")
        runner = load_runner(root, tag)
        context = {
            "tag": tag, "spec": spec, "root": root, "run_name": run_name,
            "result_branch": branch, "runner": runner, "reports": [],
            "finalized": False,
        }
        context["args"] = method_args(args, runner, output, spec)
        contexts[tag] = context
        outputs.append(output)

    preflight = validate_preflight(args, contexts)
    started_at = datetime.datetime.now().astimezone()
    for context in contexts.values():
        output = context["args"].output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=False, exist_ok=False)
        manifest = context_manifest(args, context, started_at)
        manifest["preflight"] = preflight
        context["manifest"] = manifest
        write_json(output / "experiment-manifest.json", manifest)
        append_jsonl(output / "runner.log", {
            "time": started_at.isoformat(), "event": "experiment_started",
            "context": context["tag"], "tasks": len(args.seeds),
            "shared_slots": args.slots,
        })

    emit_lock = threading.Lock()

    def emit(event, **fields):
        record = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "event": event, **fields,
        }
        with emit_lock:
            for output in outputs:
                append_jsonl(output / "orchestration.jsonl", record)
            print(json.dumps(record, allow_nan=False), flush=True)

    queue = build_ordered_tasks(args.seeds)
    active = 0
    max_active = 0
    active_lock = threading.Lock()
    monitor_state = {"max_sumo": 0, "violation": None}
    cleanup_processes = {}
    cleanup_statuses = {}

    def execute(tag, seed, queue_index):
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
            active_now = active
        started = time.monotonic()
        emit("simulation_started", context=tag, seed=seed,
             queue_index=queue_index, active_runs=active_now)
        context = contexts[tag]
        try:
            report = context["runner"].run_task(
                (context["spec"]["case"], seed), context["args"]
            )
        except Exception as error:
            report = {"case": context["spec"]["case"], "seed": seed, "error": repr(error)}
        finished = time.monotonic()
        with active_lock:
            active -= 1
            active_now = active
        emit(
            "simulation_finished", context=tag, seed=seed,
            queue_index=queue_index, active_runs=active_now,
            exit_code=report.get("exit_code"),
            source_unchanged=report.get("source_unchanged"),
            error=report.get("error"), elapsed_seconds=finished - started,
        )
        return tag, seed, report, finished

    def report_failed(report):
        return report.get("exit_code") != 0 or report.get("source_unchanged") is not True

    def finalize_context(tag, forced_status=None):
        context = contexts[tag]
        if context["finalized"]:
            return
        reports = sorted(context["reports"], key=lambda item: item["seed"])
        failures = [report for report in reports if report_failed(report)]
        if forced_status is not None:
            status = forced_status
        elif len(reports) != len(args.seeds):
            status = "incomplete"
        else:
            status = "failed" if failures else "completed"
        finished_at = datetime.datetime.now().astimezone()
        write_json(context["args"].output / "summary.json", reports)
        context["manifest"].update(
            status=status, finished_at=finished_at.isoformat(),
            finished_epoch=finished_at.timestamp(),
            elapsed_seconds=finished_at.timestamp() - started_at.timestamp(),
            completed_simulations=len(reports) - len(failures),
            failed_simulations=len(failures),
            missing_simulations=len(args.seeds) - len(reports),
            summary_file="summary.json", runner_log="runner.log",
            max_shared_active_runs=max_active,
            max_machine_sumo_processes=monitor_state["max_sumo"],
            machine_slot_violation=monitor_state["violation"],
        )
        write_json(context["args"].output / "experiment-manifest.json", context["manifest"])
        context["finalized"] = True
        emit("context_finished", context=tag, status=status,
             completed=context["manifest"]["completed_simulations"],
             failed=context["manifest"]["failed_simulations"])

    def eval_contexts(eval_name):
        return [context for context in contexts.values() if context["spec"]["eval"] == eval_name]

    def start_cleanup(eval_name):
        selected = eval_contexts(eval_name)
        if eval_name in cleanup_processes or not all(c["finalized"] for c in selected):
            return
        if not all(c["manifest"]["status"] == "completed" for c in selected):
            cleanup_statuses[eval_name] = "skipped-incomplete"
            emit("cleanup_skipped", eval=eval_name, reason="incomplete-or-failed-context")
            return
        script = Path(__file__).with_name("finalize_eval35_lambda0525_comparison.py")
        command = [str(args.python), str(script), "--eval", eval_name,
                   "--source-commit", preflight["source_commit"],
                   "--workers", str(args.cleanup_workers)]
        if args.push_results:
            command.append("--push")
        for context in selected:
            command.extend([
                "--context", context["tag"], str(context["root"]),
                context["run_name"], context["result_branch"],
            ])
        prefix = []
        if shutil.which("nice"):
            prefix.extend(["nice", "-n", "10"])
        if shutil.which("ionice"):
            prefix.extend(["ionice", "-c2", "-n7"])
        process = subprocess.Popen(prefix + command)
        cleanup_processes[eval_name] = process
        cleanup_statuses[eval_name] = "running"
        emit("cleanup_started", eval=eval_name, pid=process.pid,
             while_simulations_active=(active > 0), command=prefix + command)

    emit("orchestration_started", source_commit=preflight["source_commit"],
         slots=args.slots,
         queue=[{"context": tag, "seed": seed} for tag, seed in queue])
    abort = False
    next_index = 0
    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.slots) as pool:
        while futures or next_index < len(queue):
            done = [future for future in futures if future.done()]
            for future in done:
                futures.pop(future)
                tag, seed, report, finished = future.result()
                contexts[tag]["reports"].append(report)
                if report_failed(report):
                    abort = True
                    emit("orchestration_abort_requested", context=tag, seed=seed,
                         exit_code=report.get("exit_code"),
                         source_unchanged=report.get("source_unchanged"),
                         error=report.get("error"))
                if len(contexts[tag]["reports"]) == len(args.seeds):
                    finalize_context(tag)
                start_cleanup("eval3")
                start_cleanup("eval5")

            sumo_count = count_sumo_processes()
            monitor_state["max_sumo"] = max(monitor_state["max_sumo"], sumo_count)
            if sumo_count > args.slots:
                monitor_state["violation"] = (
                    f"machine-wide SUMO count {sumo_count} exceeded {args.slots}"
                )
                abort = True
                emit("machine_slot_limit_exceeded", count=sumo_count, limit=args.slots)

            capacity = args.slots - len(futures)
            while not abort and capacity > 0 and next_index < len(queue):
                tag, seed = queue[next_index]
                futures[pool.submit(execute, tag, seed, next_index)] = (tag, seed)
                emit("slot_filled", context=tag, seed=seed,
                     queue_index=next_index, managed_active=len(futures))
                next_index += 1
                capacity -= 1

            if abort and not futures:
                break
            if futures:
                concurrent.futures.wait(
                    futures, timeout=0.25,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
            else:
                time.sleep(0.25)

    for tag in contexts:
        if not contexts[tag]["finalized"]:
            finalize_context(tag, forced_status="incomplete" if abort else None)
    start_cleanup("eval3")
    start_cleanup("eval5")

    for eval_name, process in cleanup_processes.items():
        returncode = process.wait()
        cleanup_statuses[eval_name] = "completed" if returncode == 0 else "failed"
        emit("cleanup_finished", eval=eval_name, returncode=returncode,
             status=cleanup_statuses[eval_name])

    emit(
        "orchestration_finished", submitted_tasks=next_index,
        total_tasks=len(queue), max_active_runs=max_active,
        max_machine_sumo_processes=monitor_state["max_sumo"],
        machine_slot_violation=monitor_state["violation"], aborted=abort,
        cleanup_statuses=cleanup_statuses,
    )
    statuses = [context["manifest"]["status"] for context in contexts.values()]
    success = (
        not abort and next_index == len(queue)
        and all(status == "completed" for status in statuses)
        and cleanup_statuses == {"eval3": "completed", "eval5": "completed"}
        and max_active <= args.slots
        and monitor_state["max_sumo"] <= args.slots
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

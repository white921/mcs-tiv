#!/usr/bin/env python3
"""Run the preregistered three-scenario lambda=0.95 final holdout."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from types import SimpleNamespace


EXPECTED_PYTHON = (3, 15, 1)
EXPECTED_SUMO = "1.28.0"
LAMBDA = 0.95
SEEDS = tuple(range(23, 33))
CONDITION_ORDER = ("eval3-500", "eval5-300", "eval7-1000")
METHOD_ORDER = ("proposal", "yamashita")
CONDITION_SPECS = {
    "eval3-500": {"case": "eval3", "flows": (500, 500, 500)},
    "eval5-300": {"case": "eval5", "flows": (300, 300, 300, 300)},
    "eval7-1000": {"case": "eval7", "flows": (1000, 1000)},
}


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def append_jsonl(path: Path, value) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, allow_nan=False) + "\n")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runner(root: Path):
    path = root / "scripts" / "run_thesis_batch.py"
    spec = importlib.util.spec_from_file_location("lambda095_holdout_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_simulation_sumo_command(command: str) -> bool:
    return bool(command.strip()) and " --version" not in command


def sumo_process_commands() -> list[str]:
    result = subprocess.run(
        ["pgrep", "-a", "-x", "sumo"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(f"pgrep failed: {result.stderr.strip()}")
    return [
        line
        for line in result.stdout.splitlines()
        if is_simulation_sumo_command(line)
    ]


def count_sumo_processes() -> int:
    return len(sumo_process_commands())


def external_sumo_commands(root: Path, commands=None) -> list[str]:
    commands = sumo_process_commands() if commands is None else commands
    managed_marker = str(root.resolve())
    return [command for command in commands if managed_marker not in command]


def available_capacity(machine_slots: int, external_count: int, managed_count: int) -> int:
    return max(0, machine_slots - external_count - managed_count)


def build_ordered_tasks(seeds=SEEDS):
    return [
        (condition, method, seed)
        for condition in CONDITION_ORDER
        for method in METHOD_ORDER
        for seed in seeds
    ]


def fixed_input_template(condition: str) -> str:
    return (
        "fixed_inputs/thesis/universal-lambda095-holdout/"
        f"{condition}/seed-{{seed}}.jsonl"
    )


def output_name(condition: str, method: str, date_tag: str) -> str:
    return (
        f"universal-lambda095-holdout-{condition}-{method}-"
        f"seeds{SEEDS[0]}-{SEEDS[-1]}-600s-{date_tag}"
    )


def method_args(
    args,
    runner,
    output: Path,
    condition: str,
    method: str,
    run_git_metadata,
):
    spec = CONDITION_SPECS[condition]
    proposal = method == "proposal"
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
        fixed_input_override=fixed_input_template(condition),
        case_flows=list(spec["flows"]),
        eval7_flows=None,
        stop_time=None,
        resume_checkpoint=None,
        paper=None,
        run_git_metadata=run_git_metadata,
    )


def resume_git_metadata(root: Path, runner):
    tracked = subprocess.run(
        ["git", "diff", "--quiet"], cwd=root, check=False
    ).returncode
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=root, check=False
    ).returncode
    if tracked != 0 or staged != 0:
        raise RuntimeError("resume root has tracked or staged changes")
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        text=True,
    ).splitlines()
    unexpected = [
        line
        for line in status
        if not line.startswith(
            "?? results/runs/universal-lambda095-holdout-"
        )
    ]
    if unexpected:
        raise RuntimeError(f"unexpected resume worktree changes: {unexpected[:10]}")
    metadata = dict(runner.git_metadata())
    metadata["dirty"] = False
    metadata["resume_with_existing_untracked_results"] = True
    return metadata


def load_completed_reports(output: Path, case: str):
    reports = []
    for seed in SEEDS:
        manifest_path = output / case / f"seed-{seed}" / "manifest.json"
        if not manifest_path.is_file():
            continue
        report = json.loads(manifest_path.read_text())
        if report.get("case") != case or report.get("seed") != seed:
            raise RuntimeError(
                f"existing run identity mismatch: {manifest_path}"
            )
        if report.get("exit_code") is None:
            raise RuntimeError(f"incomplete existing run cannot be retried: {manifest_path}")
        if report.get("exit_code") != 0 or report.get("source_unchanged") is not True:
            raise RuntimeError(f"failed existing run cannot be retried: {manifest_path}")
        reports.append(report)
    return reports


def context_manifest(args, context, started_at):
    condition = context["condition"]
    method = context["method"]
    spec = CONDITION_SPECS[condition]
    return {
        "schema_version": 1,
        "record_type": "experiment-run",
        "experiment_id": context["args"].output.name,
        "status": "running",
        "classification": "formal",
        "started_at": started_at.isoformat(),
        "started_epoch": started_at.timestamp(),
        "directory": str(context["args"].output),
        "condition": condition,
        "case": spec["case"],
        "flows_vph": list(spec["flows"]),
        "method": (
            "normalized-deceleration-propagation"
            if method == "proposal"
            else "yamashita-tivtep"
        ),
        "requested_decision_method": "tivtep",
        "deceleration_convex_lambda": LAMBDA if method == "proposal" else None,
        "tasks": [{"case": spec["case"], "seed": seed} for seed in SEEDS],
        "duration_s": 600.0,
        "bus_share": 0.25,
        "workers": args.slots,
        "scheduler": {
            "type": "condition-method-seed-work-conserving-shared-queue",
            "slots": args.slots,
            "condition_order": list(CONDITION_ORDER),
            "method_order": list(METHOD_ORDER),
            "seed_order": list(SEEDS),
            "machine_wide_limit": args.slots,
            "orchestration_log": "orchestration.jsonl",
        },
        "diagnostic_traces": True,
        "checkpoint_interval_s": 60.0,
        "git": context["args"].run_git_metadata,
    }


def validate_sumo_home(sumo_home: Path) -> None:
    required = (
        sumo_home / "bin" / "sumo",
        sumo_home / "tools" / "traci" / "__init__.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"invalid SUMO_HOME; missing: {missing}")


def validate_preflight(args, root: Path, runner, contexts):
    validate_sumo_home(args.sumo_home)
    version_text = subprocess.check_output(
        [str(args.python), "-c", "import platform; print(platform.python_version())"],
        text=True,
    ).strip()
    if tuple(int(part) for part in version_text.split(".")) != EXPECTED_PYTHON:
        raise RuntimeError(f"Python must be 3.15.1, got {version_text}")
    sumo_output = subprocess.check_output(
        [str(args.sumo_home / "bin" / "sumo"), "--version"], text=True
    )
    first_line = sumo_output.splitlines()[0]
    if not re.search(rf"\b{re.escape(EXPECTED_SUMO)}\b", first_line):
        raise RuntimeError(f"SUMO must be {EXPECTED_SUMO}: {first_line}")
    environment = os.environ.copy()
    tools_path = str(args.sumo_home / "tools")
    environment["PYTHONPATH"] = (
        tools_path
        if not environment.get("PYTHONPATH")
        else f"{tools_path}:{environment['PYTHONPATH']}"
    )
    subprocess.run(
        [str(args.python), "-c", "import traci; print(traci.__file__)"],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    existing_commands = sumo_process_commands()
    existing_sumo = len(existing_commands)
    if existing_sumo > args.allow_existing_sumo:
        raise RuntimeError(
            f"refusing to start with {existing_sumo} existing SUMO process(es); "
            f"allowed {args.allow_existing_sumo}"
        )
    unexpected = [
        command
        for command in existing_commands
        if not args.allowed_external_fragment
        or args.allowed_external_fragment not in command
    ]
    if unexpected:
        raise RuntimeError(f"unexpected existing SUMO process(es): {unexpected}")

    metadata_values = {
        json.dumps(context["args"].run_git_metadata, sort_keys=True)
        for context in contexts.values()
    }
    if len(metadata_values) != 1:
        raise RuntimeError("context Git metadata differs before launch")
    metadata = json.loads(next(iter(metadata_values)))
    if metadata["commit"] is None or metadata["dirty"] is not False:
        raise RuntimeError(f"source root is not a clean Git commit: {metadata}")
    fixed_input_hashes = {}
    for condition in CONDITION_ORDER:
        spec = CONDITION_SPECS[condition]
        for seed in SEEDS:
            details = runner.fixed_input_details(
                spec["case"],
                seed,
                600.0,
                "fixed",
                prefix_duration=600.0,
                source_root=root,
                flows=spec["flows"],
                relative_path_override=fixed_input_template(condition),
            )
            fixed_input_hashes[f"{condition}/seed-{seed}"] = details["sha256"]
    scheduler_hash = file_sha256(Path(__file__).resolve())
    runner_hash = file_sha256(root / "scripts" / "run_thesis_batch.py")
    return {
        "source_commit": metadata["commit"],
        "python_version": version_text,
        "sumo_version": EXPECTED_SUMO,
        "existing_sumo_processes": existing_sumo,
        "existing_sumo_commands": existing_commands,
        "allowed_existing_sumo_processes": args.allow_existing_sumo,
        "allowed_external_fragment": args.allowed_external_fragment,
        "runner_sha256": runner_hash,
        "scheduler_sha256": scheduler_hash,
        "fixed_input_sha256": fixed_input_hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--date-tag", required=True)
    parser.add_argument("--slots", type=int, default=15)
    parser.add_argument("--allow-existing-sumo", type=int, default=0)
    parser.add_argument("--allowed-external-fragment")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if args.slots != 15:
        parser.error("this formal scheduler requires exactly 15 slots")
    if not 0 <= args.allow_existing_sumo < args.slots:
        parser.error("--allow-existing-sumo must be between 0 and 14")
    if args.allow_existing_sumo and not args.allowed_external_fragment:
        parser.error(
            "--allowed-external-fragment is required with --allow-existing-sumo"
        )
    if not args.allow_existing_sumo and args.allowed_external_fragment:
        parser.error(
            "--allowed-external-fragment requires --allow-existing-sumo"
        )
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"root does not exist: {root}")

    runner = load_runner(root)
    run_git_metadata = (
        resume_git_metadata(root, runner) if args.resume else runner.git_metadata()
    )
    contexts = {}
    outputs = []
    for condition in CONDITION_ORDER:
        for method in METHOD_ORDER:
            output = root / "results" / "runs" / output_name(
                condition, method, args.date_tag
            )
            if output.exists() and not args.resume:
                parser.error(f"output already exists: {output}")
            if args.resume and output.exists():
                manifest_path = output / "experiment-manifest.json"
                if not manifest_path.is_file():
                    parser.error(f"resume output lacks experiment manifest: {output}")
                manifest = json.loads(manifest_path.read_text())
                reports = load_completed_reports(
                    output, CONDITION_SPECS[condition]["case"]
                )
            else:
                manifest = None
                reports = []
            context = {
                "condition": condition,
                "method": method,
                "reports": reports,
                "finalized": len(reports) == len(SEEDS),
                "manifest": manifest,
            }
            context["args"] = method_args(
                args,
                runner,
                output,
                condition,
                method,
                run_git_metadata,
            )
            contexts[(condition, method)] = context
            outputs.append(output)

    preflight = validate_preflight(args, root, runner, contexts)
    completed_tasks = {
        (condition, method, report["seed"])
        for (condition, method), context in contexts.items()
        for report in context["reports"]
    }
    queue = [
        task for task in build_ordered_tasks() if task not in completed_tasks
    ]
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "preflight-passed",
                    "classification": "formal",
                    "lambda": LAMBDA,
                    "conditions": list(CONDITION_ORDER),
                    "methods": list(METHOD_ORDER),
                    "seeds": list(SEEDS),
                    "total_tasks": len(build_ordered_tasks()),
                    "completed_tasks_before_start": len(completed_tasks),
                    "remaining_tasks": len(queue),
                    "resume": args.resume,
                    "slots": args.slots,
                    **preflight,
                },
                allow_nan=False,
            )
        )
        return 0

    started_at = datetime.datetime.now().astimezone()
    for context in contexts.values():
        output = context["args"].output
        if output.exists():
            manifest = context["manifest"]
            if manifest.get("git", {}).get("commit") != preflight["source_commit"]:
                raise RuntimeError(f"resume source commit mismatch: {output}")
            if context["finalized"]:
                continue
            manifest.update(
                status="running",
                resumed_at=started_at.isoformat(),
                resume_count=int(manifest.get("resume_count", 0)) + 1,
                completed_before_resume=len(context["reports"]),
                preflight=preflight,
            )
            write_json(output / "experiment-manifest.json", manifest)
            append_jsonl(
                output / "runner.log",
                {
                    "time": started_at.isoformat(),
                    "event": "experiment_resumed",
                    "condition": context["condition"],
                    "method": context["method"],
                    "completed_before_resume": len(context["reports"]),
                    "remaining_tasks": len(SEEDS) - len(context["reports"]),
                    "shared_slots": args.slots,
                },
            )
            continue
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=False, exist_ok=False)
        manifest = context_manifest(args, context, started_at)
        manifest["preflight"] = preflight
        context["manifest"] = manifest
        write_json(output / "experiment-manifest.json", manifest)
        append_jsonl(
            output / "runner.log",
            {
                "time": started_at.isoformat(),
                "event": "experiment_started",
                "condition": context["condition"],
                "method": context["method"],
                "tasks": len(SEEDS),
                "shared_slots": args.slots,
            },
        )

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

    active = 0
    max_active = 0
    active_lock = threading.Lock()
    monitor_state = {"max_sumo": 0, "violation": None}
    stop_monitor = threading.Event()

    def monitor_sumo():
        while not stop_monitor.wait(0.5):
            try:
                commands = sumo_process_commands()
            except Exception as error:
                monitor_state["violation"] = repr(error)
                emit("sumo_monitor_error", error=repr(error))
                return
            count = len(commands)
            monitor_state["max_sumo"] = max(monitor_state["max_sumo"], count)
            external = external_sumo_commands(root, commands)
            unknown_external = [
                command
                for command in external
                if not args.allowed_external_fragment
                or args.allowed_external_fragment not in command
            ]
            if unknown_external:
                monitor_state["violation"] = (
                    f"unexpected external SUMO process(es): {unknown_external}"
                )
                emit(
                    "unexpected_external_sumo",
                    commands=unknown_external,
                )
                return
            if count > args.slots:
                monitor_state["violation"] = (
                    f"SUMO count {count} exceeded {args.slots}"
                )
                emit("machine_slot_limit_exceeded", count=count, limit=args.slots)
                return

    monitor_thread = threading.Thread(target=monitor_sumo, daemon=True)
    monitor_thread.start()

    def execute(condition, method, seed, queue_index):
        nonlocal active, max_active
        context = contexts[(condition, method)]
        with active_lock:
            active += 1
            max_active = max(max_active, active)
            active_now = active
        started = time.monotonic()
        emit(
            "simulation_started",
            condition=condition,
            method=method,
            seed=seed,
            queue_index=queue_index,
            active_runs=active_now,
        )
        try:
            report = runner.run_task(
                (CONDITION_SPECS[condition]["case"], seed), context["args"]
            )
        except Exception as error:
            report = {
                "case": CONDITION_SPECS[condition]["case"],
                "seed": seed,
                "error": repr(error),
            }
        with active_lock:
            active -= 1
            active_now = active
        emit(
            "simulation_finished",
            condition=condition,
            method=method,
            seed=seed,
            queue_index=queue_index,
            active_runs=active_now,
            exit_code=report.get("exit_code"),
            source_unchanged=report.get("source_unchanged"),
            error=report.get("error"),
            elapsed_seconds=time.monotonic() - started,
        )
        return condition, method, report

    def failed(report):
        return (
            report.get("exit_code") != 0
            or report.get("source_unchanged") is not True
        )

    def finalize_context(condition, method, forced_status=None):
        context = contexts[(condition, method)]
        if context["finalized"]:
            return
        reports = sorted(context["reports"], key=lambda report: report["seed"])
        failures = [report for report in reports if failed(report)]
        if forced_status is not None:
            status = forced_status
        elif len(reports) != len(SEEDS):
            status = "incomplete"
        else:
            status = "failed" if failures else "completed"
        finished_at = datetime.datetime.now().astimezone()
        write_json(context["args"].output / "summary.json", reports)
        context["manifest"].update(
            status=status,
            finished_at=finished_at.isoformat(),
            finished_epoch=finished_at.timestamp(),
            elapsed_seconds=(
                finished_at.timestamp()
                - float(context["manifest"].get("started_epoch", started_at.timestamp()))
            ),
            completed_simulations=len(reports) - len(failures),
            failed_simulations=len(failures),
            missing_simulations=len(SEEDS) - len(reports),
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
        context["finalized"] = True
        emit(
            "context_finished",
            condition=condition,
            method=method,
            status=status,
            completed=context["manifest"]["completed_simulations"],
            failed=context["manifest"]["failed_simulations"],
            missing=context["manifest"]["missing_simulations"],
        )

    emit(
        "orchestration_started",
        source_commit=preflight["source_commit"],
        classification="formal",
        lambda_value=LAMBDA,
        resume=args.resume,
        completed_tasks_before_start=len(completed_tasks),
        slots=args.slots,
        total_tasks=len(build_ordered_tasks()),
        remaining_tasks=len(queue),
        condition_order=list(CONDITION_ORDER),
        method_order=list(METHOD_ORDER),
        seed_order=list(SEEDS),
    )
    abort = False
    next_index = 0
    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.slots) as pool:
        while futures or next_index < len(queue):
            done = [future for future in futures if future.done()]
            for future in done:
                futures.pop(future)
                condition, method, report = future.result()
                context = contexts[(condition, method)]
                context["reports"].append(report)
                if failed(report):
                    abort = True
                    emit(
                        "orchestration_abort_requested",
                        condition=condition,
                        method=method,
                        seed=report.get("seed"),
                        exit_code=report.get("exit_code"),
                        source_unchanged=report.get("source_unchanged"),
                        error=report.get("error"),
                    )
                if len(context["reports"]) == len(SEEDS):
                    finalize_context(condition, method)

            if monitor_state["violation"] is not None:
                abort = True
            commands = sumo_process_commands()
            external = external_sumo_commands(root, commands)
            unknown_external = [
                command
                for command in external
                if not args.allowed_external_fragment
                or args.allowed_external_fragment not in command
            ]
            if unknown_external:
                abort = True
                monitor_state["violation"] = (
                    f"unexpected external SUMO process(es): {unknown_external}"
                )
                emit("unexpected_external_sumo", commands=unknown_external)
            capacity = available_capacity(
                args.slots, len(external), len(futures)
            )
            while not abort and capacity > 0 and next_index < len(queue):
                condition, method, seed = queue[next_index]
                futures[pool.submit(
                    execute, condition, method, seed, next_index
                )] = (condition, method, seed)
                emit(
                    "slot_filled",
                    condition=condition,
                    method=method,
                    seed=seed,
                    queue_index=next_index,
                    managed_active=len(futures),
                    external_sumo_processes=len(external),
                    machine_slot_limit=args.slots,
                )
                next_index += 1
                capacity -= 1
            if abort and not futures:
                break
            if futures:
                concurrent.futures.wait(
                    futures,
                    timeout=0.25,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
            else:
                time.sleep(0.25)

    stop_monitor.set()
    monitor_thread.join(timeout=2)
    for condition in CONDITION_ORDER:
        for method in METHOD_ORDER:
            if not contexts[(condition, method)]["finalized"]:
                finalize_context(
                    condition,
                    method,
                    forced_status="incomplete" if abort else None,
                )
    statuses = {
        f"{condition}-{method}": contexts[(condition, method)]["manifest"][
            "status"
        ]
        for condition in CONDITION_ORDER
        for method in METHOD_ORDER
    }
    emit(
        "orchestration_finished",
        submitted_tasks=next_index,
        remaining_tasks_at_start=len(queue),
        total_tasks=len(build_ordered_tasks()),
        max_active_runs=max_active,
        max_machine_sumo_processes=monitor_state["max_sumo"],
        machine_slot_violation=monitor_state["violation"],
        statuses=statuses,
        aborted=abort,
    )
    success = (
        not abort
        and next_index == len(queue)
        and all(status == "completed" for status in statuses.values())
        and max_active <= args.slots
        and monitor_state["max_sumo"] <= args.slots
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

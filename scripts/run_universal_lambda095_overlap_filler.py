#!/usr/bin/env python3
"""Fill spare SUMO slots without duplicating the already-running holdout tasks."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import threading
import time


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def append_jsonl(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, allow_nan=False) + "\n")


def run_directory(root: Path, queue, task, date_tag: str) -> Path:
    condition, method, seed = task
    output = root / "results" / "runs" / queue.output_name(
        condition, method, date_tag
    )
    case = queue.CONDITION_SPECS[condition]["case"]
    return output / case / f"seed-{seed}"


def command_matches_run(command: str, run: Path) -> bool:
    return str(run.resolve()) in command


def classify_existing_tasks(root: Path, queue, date_tag: str, commands):
    completed = set()
    running = set()
    queued = []
    reports = []
    for task in queue.build_ordered_tasks():
        condition, method, seed = task
        run = run_directory(root, queue, task, date_tag)
        manifest_path = run / "manifest.json"
        is_running = any(command_matches_run(command, run) for command in commands)
        if manifest_path.is_file():
            report = json.loads(manifest_path.read_text())
            expected_case = queue.CONDITION_SPECS[condition]["case"]
            if report.get("case") != expected_case or report.get("seed") != seed:
                raise RuntimeError(f"existing run identity mismatch: {manifest_path}")
            if report.get("exit_code") == 0 and report.get("source_unchanged") is True:
                completed.add(task)
                reports.append(report)
                continue
            if report.get("exit_code") is None and is_running:
                running.add(task)
                continue
            if report.get("exit_code") != 0 or report.get("source_unchanged") is not True:
                raise RuntimeError(f"failed or incomplete run cannot be retried: {manifest_path}")
        if is_running:
            running.add(task)
            continue
        if run.exists():
            raise RuntimeError(f"orphaned run directory cannot be retried: {run}")
        queued.append(task)
    return completed, running, queued, reports


def validate_source(root: Path, queue, source_commit: str, date_tag: str):
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    if actual != source_commit:
        raise RuntimeError(
            f"experiment source commit changed: expected {source_commit}, got {actual}"
        )
    queue.resume_git_metadata(root, queue.load_runner(root))
    git_metadata = None
    for condition in queue.CONDITION_ORDER:
        for method in queue.METHOD_ORDER:
            output = root / "results" / "runs" / queue.output_name(
                condition, method, date_tag
            )
            manifest_path = output / "experiment-manifest.json"
            if not manifest_path.is_file():
                raise RuntimeError(f"missing experiment manifest: {manifest_path}")
            manifest = json.loads(manifest_path.read_text())
            current = manifest.get("git")
            if not isinstance(current, dict):
                raise RuntimeError(f"missing Git metadata: {manifest_path}")
            if current.get("commit") != source_commit or current.get("dirty") is not False:
                raise RuntimeError(f"invalid source metadata: {manifest_path}")
            if git_metadata is None:
                git_metadata = current
            elif current != git_metadata:
                raise RuntimeError("experiment manifests disagree on Git metadata")
    return git_metadata


def validate_runtime(args) -> None:
    version = subprocess.check_output(
        [str(args.python), "-c", "import platform; print(platform.python_version())"],
        text=True,
    ).strip()
    if version != "3.15.1":
        raise RuntimeError(f"Python must be 3.15.1, got {version}")
    first_line = subprocess.check_output(
        [str(args.sumo_home / "bin" / "sumo"), "--version"], text=True
    ).splitlines()[0]
    if "1.28.0" not in first_line:
        raise RuntimeError(f"SUMO must be 1.28.0: {first_line}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--date-tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--slots", type=int, default=15)
    parser.add_argument("--allowed-external-fragment", action="append", default=[])
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if args.slots != 15:
        parser.error("this filler requires exactly 15 machine-wide slots")

    root = args.root.resolve()
    control_root = Path(__file__).resolve().parents[1]
    queue = load_module(
        "lambda095_holdout_queue",
        control_root / "scripts" / "run_universal_lambda095_holdout.py",
    )
    runner = queue.load_runner(root)
    git_metadata = validate_source(root, queue, args.source_commit, args.date_tag)
    validate_runtime(args)

    commands = queue.sumo_process_commands()
    completed, running, tasks, _ = classify_existing_tasks(
        root, queue, args.date_tag, commands
    )
    allowed_fragments = [str(root), *args.allowed_external_fragment]
    unexpected = [
        command
        for command in commands
        if not any(fragment in command for fragment in allowed_fragments)
    ]
    if unexpected:
        raise RuntimeError(f"unexpected existing SUMO process(es): {unexpected}")

    contexts = {}
    for condition in queue.CONDITION_ORDER:
        for method in queue.METHOD_ORDER:
            output = root / "results" / "runs" / queue.output_name(
                condition, method, args.date_tag
            )
            contexts[(condition, method)] = queue.method_args(
                args, runner, output, condition, method, git_metadata
            )

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "preflight-passed",
                    "source_commit": args.source_commit,
                    "completed_tasks": len(completed),
                    "running_tasks": [list(task) for task in sorted(running)],
                    "queued_tasks": len(tasks),
                    "existing_sumo_processes": len(commands),
                    "slots": args.slots,
                },
                allow_nan=False,
            )
        )
        return 0

    log = (
        root
        / "results"
        / "runs"
        / f"universal-lambda095-holdout-overlap-filler-{args.date_tag}.jsonl"
    )
    log_lock = threading.Lock()

    def emit(event, **fields):
        record = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "event": event,
            **fields,
        }
        with log_lock:
            append_jsonl(log, record)
            print(json.dumps(record, allow_nan=False), flush=True)

    emit(
        "overlap_filler_started",
        source_commit=args.source_commit,
        completed_before_start=len(completed),
        running_elsewhere=len(running),
        queued_tasks=len(tasks),
        slots=args.slots,
    )

    def execute(task, queue_index):
        condition, method, seed = task
        started = time.monotonic()
        emit(
            "simulation_started",
            condition=condition,
            method=method,
            seed=seed,
            queue_index=queue_index,
        )
        try:
            report = runner.run_task(
                (queue.CONDITION_SPECS[condition]["case"], seed),
                contexts[(condition, method)],
            )
        except Exception as error:
            report = {
                "case": queue.CONDITION_SPECS[condition]["case"],
                "seed": seed,
                "error": repr(error),
            }
        emit(
            "simulation_finished",
            condition=condition,
            method=method,
            seed=seed,
            queue_index=queue_index,
            exit_code=report.get("exit_code"),
            source_unchanged=report.get("source_unchanged"),
            error=report.get("error"),
            elapsed_seconds=time.monotonic() - started,
        )
        return task, report

    def failed(report):
        return report.get("exit_code") != 0 or report.get("source_unchanged") is not True

    next_index = 0
    futures = {}
    abort = False
    max_machine_sumo = len(commands)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.slots) as pool:
        while futures or next_index < len(tasks):
            done = [future for future in futures if future.done()]
            for future in done:
                futures.pop(future)
                task, report = future.result()
                if failed(report):
                    abort = True
                    emit(
                        "overlap_filler_abort_requested",
                        condition=task[0],
                        method=task[1],
                        seed=task[2],
                        exit_code=report.get("exit_code"),
                        source_unchanged=report.get("source_unchanged"),
                        error=report.get("error"),
                    )

            commands = queue.sumo_process_commands()
            max_machine_sumo = max(max_machine_sumo, len(commands))
            if len(commands) > args.slots:
                abort = True
                emit(
                    "machine_slot_limit_exceeded",
                    count=len(commands),
                    limit=args.slots,
                )
            unexpected = [
                command
                for command in commands
                if not any(fragment in command for fragment in allowed_fragments)
            ]
            if unexpected:
                abort = True
                emit("unexpected_external_sumo", commands=unexpected)

            active_runs = {
                future: run_directory(root, queue, task, args.date_tag)
                for future, task in futures.items()
            }
            managed_sumo = sum(
                1
                for command in commands
                if any(
                    command_matches_run(command, run)
                    for run in active_runs.values()
                )
            )
            external_sumo = len(commands) - managed_sumo
            capacity = queue.available_capacity(
                args.slots, external_sumo, len(futures)
            )
            while not abort and capacity > 0 and next_index < len(tasks):
                task = tasks[next_index]
                future = pool.submit(execute, task, next_index)
                futures[future] = task
                emit(
                    "slot_filled",
                    condition=task[0],
                    method=task[1],
                    seed=task[2],
                    queue_index=next_index,
                    managed_active=len(futures),
                    external_sumo_processes=external_sumo,
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

    emit(
        "overlap_filler_finished",
        submitted_tasks=next_index,
        queued_tasks=len(tasks),
        max_machine_sumo_processes=max_machine_sumo,
        aborted=abort,
    )
    return 0 if not abort and next_index == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

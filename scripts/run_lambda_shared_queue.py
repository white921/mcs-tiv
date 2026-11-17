#!/usr/bin/env python3
"""Run ordered lambda candidates through one machine-wide shared slot queue.

The queue is lambda-major and then seed-major.  It can join an already-running
first lambda batch: the active runs in that external batch occupy slots, and
each completed external or managed run immediately releases one slot for the
next queued task.
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import threading
import time
from types import SimpleNamespace


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


def load_runner(root, tag):
    path = root / "scripts" / "run_thesis_batch.py"
    spec = importlib.util.spec_from_file_location(f"lambda_runner_{tag}", path)
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


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def external_state(output):
    manifest_path = output / "experiment-manifest.json"
    manifest = read_json(manifest_path)
    active = 0
    for path in output.rglob("manifest.json"):
        if read_json(path).get("exit_code") is None:
            active += 1
    return manifest.get("status"), active


def base_args(args, runner, output, lambda_value):
    return SimpleNamespace(
        output=output,
        sumo_home=args.sumo_home,
        decision_method="documented",
        deceleration_active=True,
        deceleration_convex_lambda=lambda_value,
        agreement_lease_seconds=0.0,
        merge_negotiation_lead_seconds=0.0,
        two_stage_merge_negotiation=False,
        diagnostic_traces=False,
        checkpoint_interval=0.0,
        python=str(args.python),
        duration=args.duration,
        bus_allocation="fixed",
        fixed_input_override=args.fixed_input_override,
        eval7_flows=list(args.eval7_flows),
        stop_time=None,
        resume_checkpoint=None,
        paper=None,
        run_git_metadata=runner.git_metadata(),
    )


def candidate_manifest(args, context, started_at):
    method_args = context["args"]
    return {
        "schema_version": 1,
        "record_type": "experiment-run",
        "experiment_id": method_args.output.name,
        "status": "running",
        "started_at": started_at.isoformat(),
        "started_epoch": started_at.timestamp(),
        "directory": str(method_args.output),
        "method": "normalized-deceleration-propagation",
        "requested_decision_method": "documented",
        "deceleration_convex_lambda": context["lambda"],
        "agreement_lease_seconds": 0.0,
        "merge_negotiation_lead_seconds": 0.0,
        "two_stage_merge_negotiation": False,
        "cases": ["eval7"],
        "eval7_flows_vph": {
            "requesting": args.eval7_flows[0],
            "accepting": args.eval7_flows[1],
        },
        "tasks": [{"case": "eval7", "seed": seed} for seed in args.seeds],
        "duration_s": args.duration,
        "stop_time_s": None,
        "workers": args.slots,
        "scheduler": {
            "type": "lambda-ordered-work-conserving-shared-queue",
            "slots": args.slots,
            "candidate_order": [item[0] for item in args.candidate],
            "seed_order": list(args.seeds),
            "external_experiment": str(args.external_output),
            "machine_wide_limit": args.slots,
            "orchestration_log": "orchestration.jsonl",
        },
        "diagnostic_traces": False,
        "checkpoint_interval_s": 0.0,
        "git": method_args.run_git_metadata,
    }


def validate_preflight(args, contexts):
    version_text = subprocess.check_output(
        [str(args.python), "-c", "import platform; print(platform.python_version())"],
        text=True,
    ).strip()
    if tuple(int(part) for part in version_text.split(".")) != EXPECTED_PYTHON:
        raise RuntimeError(f"Python must be 3.15.1, got {version_text}")
    sumo_first_line = subprocess.check_output(
        [str(args.sumo_home / "bin" / "sumo"), "--version"], text=True
    ).splitlines()[0]
    if EXPECTED_SUMO not in sumo_first_line:
        raise RuntimeError(f"SUMO must be {EXPECTED_SUMO}: {sumo_first_line}")

    external_status, external_active = external_state(args.external_output)
    if external_status not in ("running", "completed"):
        raise RuntimeError(f"external experiment status is {external_status!r}")
    existing_sumo = count_sumo_processes()
    if existing_sumo != external_active:
        raise RuntimeError(
            "existing SUMO processes do not match the external batch: "
            f"sumo={existing_sumo}, external_active={external_active}"
        )
    if existing_sumo > args.slots:
        raise RuntimeError("existing SUMO processes exceed the slot limit")

    commits = set()
    runner_hashes = set()
    input_hashes = {seed: set() for seed in args.seeds}
    for tag, context in contexts.items():
        metadata = context["args"].run_git_metadata
        if metadata["commit"] is None or metadata["dirty"] is not False:
            raise RuntimeError(f"lambda {tag} worktree is not clean: {metadata}")
        commits.add(metadata["commit"])
        root = context["root"]
        runner_hashes.add(file_sha256(root / "scripts" / "run_thesis_batch.py"))
        runner = context["runner"]
        built = runner.build_tasks(
            ["eval7"], seeds=args.seeds, eval7_flows=args.eval7_flows
        )
        if built != [("eval7", seed) for seed in args.seeds]:
            raise RuntimeError(f"unexpected task selection for lambda {tag}")
        for seed in args.seeds:
            details = runner.fixed_input_details(
                "eval7",
                seed,
                args.duration,
                "fixed",
                prefix_duration=args.duration,
                source_root=root,
                flows=args.eval7_flows,
                relative_path_override=args.fixed_input_override,
            )
            input_hashes[seed].add(details["sha256"])
    if len(commits) != 1:
        raise RuntimeError(f"worktrees do not share one commit: {sorted(commits)}")
    if len(runner_hashes) != 1:
        raise RuntimeError("runner source differs between worktrees")
    mismatched = [seed for seed, hashes in input_hashes.items() if len(hashes) != 1]
    if mismatched:
        raise RuntimeError(f"fixed input hashes differ for seeds: {mismatched}")
    return {
        "source_commit": next(iter(commits)),
        "python_version": version_text,
        "sumo_version": EXPECTED_SUMO,
        "external_active_at_start": external_active,
        "existing_sumo_processes": existing_sumo,
        "fixed_input_sha256": {
            str(seed): next(iter(hashes)) for seed, hashes in input_hashes.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        action="append",
        nargs=4,
        metavar=("TAG", "LAMBDA", "ROOT", "RUN_NAME"),
        required=True,
    )
    parser.add_argument("--external-output", type=Path, required=True)
    parser.add_argument("--external-unit")
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument(
        "--fixed-input-override",
        default=(
            "fixed_inputs/thesis/eval7-flow-sweep/"
            "requesting-1000-accepting-1000/seed-{seed}.jsonl"
        ),
    )
    parser.add_argument("--eval7-flows", type=int, nargs=2, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--slots", type=int, default=15)
    args = parser.parse_args()

    if args.slots != 15:
        parser.error("this scheduler requires exactly 15 slots")
    if len(args.seeds) != 10 or len(set(args.seeds)) != 10:
        parser.error("--seeds must contain exactly 10 unique values")
    if not 0 < args.duration <= 600:
        parser.error("--duration must be in (0, 600]")

    parsed_candidates = []
    seen_tags = set()
    previous_lambda = None
    for tag, lambda_text, root_text, run_name in args.candidate:
        lambda_value = float(lambda_text)
        if tag in seen_tags:
            parser.error(f"duplicate candidate tag: {tag}")
        if not 0 <= lambda_value <= 1:
            parser.error(f"lambda must be in [0,1]: {lambda_value}")
        if previous_lambda is not None and lambda_value <= previous_lambda:
            parser.error("candidates must be strictly increasing by lambda")
        root = Path(root_text).resolve()
        if not root.is_dir():
            parser.error(f"candidate root does not exist: {root}")
        parsed_candidates.append((tag, lambda_value, root, run_name))
        seen_tags.add(tag)
        previous_lambda = lambda_value

    args.external_output = args.external_output.resolve()
    contexts = {}
    outputs = []
    for tag, lambda_value, root, run_name in parsed_candidates:
        output = root / "results" / "runs" / run_name
        if output.exists():
            parser.error(f"output already exists: {output}")
        runner = load_runner(root, tag)
        method_args = base_args(args, runner, output, lambda_value)
        contexts[tag] = {
            "tag": tag,
            "lambda": lambda_value,
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
    for context in contexts.values():
        output = context["args"].output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=False, exist_ok=False)
        manifest = candidate_manifest(args, context, started_at)
        manifest["preflight"] = preflight
        context["manifest"] = manifest
        write_json(output / "experiment-manifest.json", manifest)
        append_jsonl(
            output / "runner.log",
            {
                "time": started_at.isoformat(),
                "event": "experiment_started",
                "lambda": context["lambda"],
                "tasks": len(args.seeds),
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

    queue = [
        (tag, seed)
        for tag, _lambda, _root, _run_name in parsed_candidates
        for seed in args.seeds
    ]
    monitor_state = {"max_sumo": preflight["existing_sumo_processes"], "violation": None}
    external_cleanup_done = False

    def execute(tag, seed, queue_index):
        context = contexts[tag]
        started = time.monotonic()
        emit(
            "simulation_started",
            tag=tag,
            lambda_value=context["lambda"],
            seed=seed,
            queue_index=queue_index,
        )
        try:
            report = context["runner"].run_task(
                ("eval7", seed), context["args"]
            )
        except Exception as error:
            report = {"case": "eval7", "seed": seed, "error": repr(error)}
        emit(
            "simulation_finished",
            tag=tag,
            lambda_value=context["lambda"],
            seed=seed,
            queue_index=queue_index,
            exit_code=report.get("exit_code"),
            source_unchanged=report.get("source_unchanged"),
            error=report.get("error"),
            elapsed_seconds=time.monotonic() - started,
        )
        return tag, seed, queue_index, report

    def report_failed(report):
        return (
            report.get("exit_code") != 0
            or report.get("source_unchanged") is not True
        )

    def finalize(tag, forced_status=None):
        context = contexts[tag]
        if context["finalized"]:
            return
        reports = sorted(context["reports"], key=lambda value: value["seed"])
        failures = [report for report in reports if report_failed(report)]
        if forced_status is not None:
            status = forced_status
        elif len(reports) < len(args.seeds):
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
            missing_simulations=len(args.seeds) - len(reports),
            summary_file="summary.json",
            runner_log="runner.log",
            max_machine_sumo_processes=monitor_state["max_sumo"],
            machine_slot_violation=monitor_state["violation"],
        )
        write_json(context["args"].output / "experiment-manifest.json", context["manifest"])
        append_jsonl(
            context["args"].output / "runner.log",
            {
                "time": finished_at.isoformat(),
                "event": "experiment_finished",
                "status": status,
                "completed": context["manifest"]["completed_simulations"],
                "failed": context["manifest"]["failed_simulations"],
                "missing": context["manifest"]["missing_simulations"],
            },
        )
        context["finalized"] = True
        emit("candidate_finished", tag=tag, lambda_value=context["lambda"], status=status)

    emit(
        "orchestration_started",
        source_commit=preflight["source_commit"],
        slots=args.slots,
        external_active=preflight["external_active_at_start"],
        queue=[{"tag": tag, "seed": seed} for tag, seed in queue],
    )

    abort = False
    next_index = 0
    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.slots) as pool:
        while futures or next_index < len(queue):
            done = [future for future in futures if future.done()]
            for future in done:
                futures.pop(future)
                tag, seed, queue_index, report = future.result()
                contexts[tag]["reports"].append(report)
                if report_failed(report):
                    abort = True
                    emit(
                        "orchestration_abort_requested",
                        tag=tag,
                        seed=seed,
                        exit_code=report.get("exit_code"),
                        source_unchanged=report.get("source_unchanged"),
                        error=report.get("error"),
                    )
                if len(contexts[tag]["reports"]) == len(args.seeds):
                    finalize(tag)

            external_status, external_active = external_state(args.external_output)
            if external_status == "failed":
                abort = True
                emit("external_experiment_failed")
            if external_status == "completed" and not external_cleanup_done:
                if args.external_unit:
                    subprocess.run(
                        [
                            "systemctl",
                            "--user",
                            "kill",
                            "--kill-who=main",
                            "--signal=SIGKILL",
                            args.external_unit,
                        ],
                        check=False,
                    )
                external_cleanup_done = True
                emit("external_experiment_completed")

            sumo_count = count_sumo_processes()
            monitor_state["max_sumo"] = max(monitor_state["max_sumo"], sumo_count)
            if sumo_count > args.slots:
                monitor_state["violation"] = (
                    f"machine-wide SUMO count {sumo_count} exceeded {args.slots}"
                )
                abort = True
                emit("machine_slot_limit_exceeded", count=sumo_count, limit=args.slots)

            capacity = args.slots - external_active - len(futures)
            while not abort and capacity > 0 and next_index < len(queue):
                tag, seed = queue[next_index]
                futures[pool.submit(execute, tag, seed, next_index)] = (
                    tag,
                    seed,
                    next_index,
                )
                emit(
                    "slot_filled",
                    tag=tag,
                    lambda_value=contexts[tag]["lambda"],
                    seed=seed,
                    queue_index=next_index,
                    external_active=external_active,
                    managed_active=len(futures),
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

    for tag in contexts:
        if not contexts[tag]["finalized"]:
            finalize(tag, forced_status="incomplete" if abort else None)
    emit(
        "orchestration_finished",
        submitted_tasks=next_index,
        total_tasks=len(queue),
        max_machine_sumo_processes=monitor_state["max_sumo"],
        machine_slot_violation=monitor_state["violation"],
        aborted=abort,
    )
    success = (
        not abort
        and next_index == len(queue)
        and all(contexts[tag]["manifest"]["status"] == "completed" for tag in contexts)
        and monitor_state["max_sumo"] <= args.slots
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

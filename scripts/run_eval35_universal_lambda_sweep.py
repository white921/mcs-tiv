#!/usr/bin/env python3
"""Run universal-lambda screening on a shared SUMO queue."""

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
SEEDS = tuple(range(13, 23))
LAMBDAS = tuple(index / 10 for index in range(11))
CONDITION_ORDER = ("eval3-500", "eval5-300")
HIGH_LAMBDAS = (0.925, 0.95, 40 / 41, 80 / 81)
MERGE_SEEDS = tuple(range(33, 43))
MERGE_FLOW_SEEDS = {
    300: MERGE_SEEDS,
    500: tuple(range(43, 48)),
    700: MERGE_SEEDS,
    1200: MERGE_SEEDS,
}
CONDITION_SPECS = {
    "eval3-500": {"case": "eval3", "flows": (500, 500, 500)},
    "eval5-300": {"case": "eval5", "flows": (300, 300, 300, 300)},
    **{
        f"eval7-{flow}": {"case": "eval7", "flows": (flow, 1000)}
        for flow in (*MERGE_FLOW_SEEDS, 1000)
    },
}


def lambda_tag(value: float) -> str:
    return f"{round(value * 100):03d}"


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, allow_nan=False) + "\n")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runner(root: Path, tag: str):
    path = root / "scripts" / "run_thesis_batch.py"
    spec = importlib.util.spec_from_file_location(f"universal_lambda_runner_{tag}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def count_sumo_processes() -> int:
    result = subprocess.run(
        ["pgrep", "-x", "sumo"], text=True, capture_output=True, check=False
    )
    if result.returncode == 1:
        return 0
    if result.returncode != 0:
        raise RuntimeError(f"pgrep failed: {result.stderr.strip()}")
    return len([line for line in result.stdout.splitlines() if line.strip()])


def fixed_input_template(condition: str) -> str:
    spec = CONDITION_SPECS[condition]
    if spec["case"] == "eval7":
        requesting, accepting = spec["flows"]
        return (
            "fixed_inputs/thesis/eval7-flow-sweep/"
            f"requesting-{requesting}-accepting-{accepting}/seed-{{seed}}.jsonl"
        )
    return (
        "fixed_inputs/thesis/eval35-paper-comparison/"
        f"{condition}/seed-{{seed}}.jsonl"
    )


def run_name(condition: str, value: float, date_tag: str, seeds=SEEDS, grid: str = "wide") -> str:
    tag = lambda_tag(value) if grid == "wide" else f"{value:.8f}".partition(".")[2]
    return (
        f"universal-lambda{tag}-{condition}-"
        f"seeds{seeds[0]}-{seeds[-1]}-600s-{date_tag}"
    )


def condition_cohorts(grid: str):
    if grid == "wide":
        return {condition: (LAMBDAS, SEEDS) for condition in CONDITION_ORDER}
    if grid == "merge-flow":
        return {f"eval7-{flow}": ((0.95,), seeds) for flow, seeds in MERGE_FLOW_SEEDS.items()}
    # The matched 600 s Eval.7 cohorts at 0.95 and 80/81 already exist.
    return {
        "eval3-500": (HIGH_LAMBDAS, SEEDS),
        "eval5-300": (HIGH_LAMBDAS, SEEDS),
        "eval7-1000": ((0.925, 40 / 41), MERGE_SEEDS),
    }


def build_ordered_tasks(grid: str = "wide") -> list[tuple[str, float, int]]:
    return [
        (condition, value, seed)
        for condition, (lambdas, seeds) in condition_cohorts(grid).items()
        for value in lambdas
        for seed in seeds
    ]


def validate_sumo_home_layout(sumo_home: Path) -> None:
    required = (
        sumo_home / "bin" / "sumo",
        sumo_home / "tools" / "traci" / "__init__.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(
            "SUMO_HOME must contain bin/sumo and tools/traci/__init__.py; "
            f"missing: {missing}"
        )


def method_args(args, runner, output: Path, condition: str, value: float):
    spec = CONDITION_SPECS[condition]
    return SimpleNamespace(
        output=output,
        sumo_home=args.sumo_home,
        decision_method="tivtep",
        deceleration_active=True,
        deceleration_convex_lambda=value,
        agreement_lease_seconds=0.0,
        merge_negotiation_lead_seconds=0.0,
        two_stage_merge_negotiation=False,
        diagnostic_traces=False,
        checkpoint_interval=0.0,
        python=str(args.python),
        duration=600.0,
        bus_allocation="fixed",
        fixed_input_override=fixed_input_template(condition),
        case_flows=list(spec["flows"]),
        eval7_flows=None,
        stop_time=None,
        resume_checkpoint=None,
        paper=None,
        run_git_metadata=runner.git_metadata(),
    )


def cohort_manifest(args, context, started_at):
    condition = context["condition"]
    spec = CONDITION_SPECS[condition]
    return {
        "schema_version": 1,
        "record_type": "experiment-run",
        "experiment_id": context["args"].output.name,
        "status": "running",
        "classification": "development-screening",
        "started_at": started_at.isoformat(),
        "started_epoch": started_at.timestamp(),
        "directory": str(context["args"].output),
        "condition": condition,
        "case": spec["case"],
        "flows_vph": list(spec["flows"]),
        "method": "normalized-deceleration-propagation",
        "requested_decision_method": "tivtep",
        "deceleration_convex_lambda": context["lambda"],
        "tasks": [{"case": spec["case"], "seed": seed} for seed in context["seeds"]],
        "duration_s": 600.0,
        "bus_share": 0.25,
        "workers": args.slots,
        "scheduler": {
            "type": "condition-lambda-seed-work-conserving-shared-queue",
            "slots": args.slots,
            "condition_order": list(args.condition_order),
            "lambda_order": list(context["lambdas"]),
            "seed_order": list(context["seeds"]),
            "machine_wide_limit": args.slots,
            "orchestration_log": "orchestration.jsonl",
            "cohort_postprocess": True,
        },
        "diagnostic_traces": False,
        "checkpoint_interval_s": 0.0,
        "git": context["args"].run_git_metadata,
    }


def validate_preflight(args, contexts):
    validate_sumo_home_layout(args.sumo_home)
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
    traci_environment = os.environ.copy()
    existing_pythonpath = traci_environment.get("PYTHONPATH")
    tools_path = str(args.sumo_home / "tools")
    traci_environment["PYTHONPATH"] = (
        tools_path if not existing_pythonpath else f"{tools_path}:{existing_pythonpath}"
    )
    subprocess.run(
        [str(args.python), "-c", "import traci; print(traci.__file__)"],
        env=traci_environment,
        text=True,
        capture_output=True,
        check=True,
    )
    existing_sumo = count_sumo_processes()
    if existing_sumo:
        raise RuntimeError(f"refusing to start with {existing_sumo} SUMO process(es)")

    commits = set()
    runner_hashes = set()
    scheduler_hashes = set()
    finalizer_hashes = set()
    fixed_input_hashes: dict[tuple[str, int], set[str]] = {}
    checked_roots = set()
    for context in contexts.values():
        metadata = context["args"].run_git_metadata
        if metadata["commit"] is None or metadata["dirty"] is not False:
            raise RuntimeError(
                f"{context['condition']} root is not a clean commit: {metadata}"
            )
        commits.add(metadata["commit"])
        root = context["root"]
        if root not in checked_roots:
            runner_hashes.add(file_sha256(root / "scripts" / "run_thesis_batch.py"))
            scheduler_hashes.add(file_sha256(root / "scripts" / Path(__file__).name))
            finalizer_hashes.add(
                file_sha256(root / "scripts" / "finalize_eval35_lambda_screening.py")
            )
            checked_roots.add(root)
        runner = context["runner"]
        condition = context["condition"]
        spec = CONDITION_SPECS[condition]
        for seed in context["seeds"]:
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
            fixed_input_hashes.setdefault((condition, seed), set()).add(details["sha256"])
    if len(commits) != 1:
        raise RuntimeError(f"condition roots differ in source commit: {sorted(commits)}")
    if len(runner_hashes) != 1 or len(scheduler_hashes) != 1 or len(finalizer_hashes) != 1:
        raise RuntimeError("runner, scheduler, or finalizer differs between roots")
    mismatched = [key for key, hashes in fixed_input_hashes.items() if len(hashes) != 1]
    if mismatched:
        raise RuntimeError(f"fixed inputs differ between candidates: {mismatched[:5]}")
    return {
        "source_commit": next(iter(commits)),
        "python_version": version_text,
        "sumo_version": EXPECTED_SUMO,
        "existing_sumo_processes": existing_sumo,
        "fixed_input_sha256": {
            f"{condition}/seed-{seed}": next(iter(hashes))
            for (condition, seed), hashes in fixed_input_hashes.items()
        },
    }


def git_save_condition(condition, root, branch, outputs, push):
    current = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    if current != branch:
        raise RuntimeError(f"{condition}: expected branch {branch}, got {current}")
    relative_outputs = [str(output.relative_to(root)) for output in outputs]
    subprocess.run(["git", "add", "-f", "--", *relative_outputs], cwd=root, check=True)
    staged = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"], cwd=root, text=True
    ).splitlines()
    if not staged or any(
        not any(path.startswith(relative + "/") for relative in relative_outputs)
        for path in staged
    ):
        raise RuntimeError(f"{condition}: unexpected staged files")
    subprocess.run(
        ["git", "commit", "-m", f"results: add {condition} universal lambda screening"],
        cwd=root,
        check=True,
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if push:
        subprocess.run(["git", "push", "origin", f"HEAD:{branch}"], cwd=root, check=True)
    return commit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--condition-root",
        action="append",
        nargs=3,
        required=True,
        metavar=("CONDITION", "ROOT", "RESULT_BRANCH"),
    )
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--system-python", type=Path, default=Path("/usr/bin/python3"))
    parser.add_argument("--date-tag", required=True)
    parser.add_argument("--grid", choices=("wide", "high", "merge-flow"), default="wide")
    parser.add_argument("--slots", type=int, choices=(15, 20), default=15)
    parser.add_argument("--cleanup-workers", type=int, default=2)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--push-results", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    plan = condition_cohorts(args.grid)
    args.condition_order = tuple(plan)
    if args.cleanup_workers < 1 or args.cleanup_workers > 2:
        parser.error("--cleanup-workers must be 1 or 2")
    supplied = {}
    for condition, root_text, branch in args.condition_root:
        if condition in supplied:
            parser.error(f"duplicate condition: {condition}")
        supplied[condition] = (Path(root_text).resolve(), branch)
    if tuple(supplied) != args.condition_order:
        parser.error("condition roots must be supplied in order: " + ", ".join(args.condition_order))

    contexts = {}
    outputs = []
    for condition, (lambdas, seeds) in plan.items():
        root, branch = supplied[condition]
        if not root.is_dir():
            parser.error(f"condition root does not exist: {root}")
        for value in lambdas:
            tag = run_name(condition, value, args.date_tag, seeds, args.grid)
            output = root / "results" / "runs" / tag
            if output.exists():
                parser.error(f"output already exists: {output}")
            runner = load_runner(root, tag)
            contexts[(condition, value)] = {
                "condition": condition,
                "lambda": value,
                "lambdas": lambdas,
                "seeds": seeds,
                "root": root,
                "branch": branch,
                "runner": runner,
                "args": method_args(args, runner, output, condition, value),
                "manifest": None,
                "reports": [],
                "finalized": False,
                "postprocess": None,
            }
            outputs.append(output)

    preflight = validate_preflight(args, contexts)
    queue = build_ordered_tasks(args.grid)
    if args.preflight_only:
        print(json.dumps({
            "status": "preflight-passed", "slots": args.slots, "total_tasks": len(queue),
            "cohorts": [
                {"condition": condition, "lambda": value, "seeds": context["seeds"]}
                for (condition, value), context in contexts.items()
            ],
            **preflight,
        }, allow_nan=False))
        return 0
    started_at = datetime.datetime.now().astimezone()
    for context in contexts.values():
        output = context["args"].output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=False, exist_ok=False)
        manifest = cohort_manifest(args, context, started_at)
        manifest["preflight"] = preflight
        context["manifest"] = manifest
        write_json(output / "experiment-manifest.json", manifest)
        append_jsonl(
            output / "runner.log",
            {
                "time": started_at.isoformat(),
                "event": "experiment_started",
                "condition": context["condition"],
                "lambda": context["lambda"],
                "tasks": len(context["seeds"]),
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
            count = count_sumo_processes()
            monitor_state["max_sumo"] = max(monitor_state["max_sumo"], count)
            if count > args.slots:
                monitor_state["violation"] = f"SUMO count {count} exceeded {args.slots}"
                emit("machine_slot_limit_exceeded", count=count, limit=args.slots)
                return

    monitor_thread = threading.Thread(target=monitor_sumo, daemon=True)
    monitor_thread.start()

    def execute(condition, value, seed, queue_index):
        nonlocal active, max_active
        context = contexts[(condition, value)]
        with active_lock:
            active += 1
            max_active = max(max_active, active)
            active_now = active
        started = time.monotonic()
        emit(
            "simulation_started",
            condition=condition,
            lambda_value=value,
            seed=seed,
            queue_index=queue_index,
            active_runs=active_now,
        )
        try:
            report = context["runner"].run_task(
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
            lambda_value=value,
            seed=seed,
            queue_index=queue_index,
            active_runs=active_now,
            exit_code=report.get("exit_code"),
            source_unchanged=report.get("source_unchanged"),
            error=report.get("error"),
            elapsed_seconds=time.monotonic() - started,
        )
        return condition, value, seed, report

    def failed(report):
        return report.get("exit_code") != 0 or report.get("source_unchanged") is not True

    def finalize_context(condition, value):
        context = contexts[(condition, value)]
        if context["finalized"]:
            return
        reports = sorted(context["reports"], key=lambda report: report["seed"])
        failures = [report for report in reports if failed(report)]
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
            missing_simulations=len(context["seeds"]) - len(reports),
            summary_file="summary.json",
            runner_log="runner.log",
            max_shared_active_runs=max_active,
            max_machine_sumo_processes=monitor_state["max_sumo"],
            machine_slot_violation=monitor_state["violation"],
        )
        write_json(context["args"].output / "experiment-manifest.json", context["manifest"])
        context["finalized"] = True
        emit(
            "cohort_finished",
            condition=condition,
            lambda_value=value,
            status=status,
            completed=context["manifest"]["completed_simulations"],
            failed=context["manifest"]["failed_simulations"],
        )

    def postprocess(condition, value):
        context = contexts[(condition, value)]
        command = [
            "nice", "-n", "10", "ionice", "-c2", "-n7",
            str(args.system_python),
            str(context["root"] / "scripts" / "finalize_eval35_lambda_screening.py"),
            "--output", str(context["args"].output),
            "--condition", condition,
            "--case", CONDITION_SPECS[condition]["case"],
            "--lambda-value", str(value),
            "--source-commit", preflight["source_commit"],
            "--seeds", *(str(seed) for seed in context["seeds"]),
        ]
        emit("cohort_postprocess_started", condition=condition, lambda_value=value)
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        emit(
            "cohort_postprocess_finished",
            condition=condition,
            lambda_value=value,
            returncode=result.returncode,
            stderr_tail=result.stderr[-1000:],
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"postprocess failed for {condition} lambda={value}: {result.stderr[-2000:]}"
            )
        return condition, value

    emit(
        "orchestration_started",
        source_commit=preflight["source_commit"],
        slots=args.slots,
        total_tasks=len(queue),
        condition_order=list(args.condition_order),
        lambda_order=sorted({value for _, value in contexts}),
        seed_order_by_condition={
            condition: seeds for condition, (_, seeds) in plan.items()
        },
        **({"seed_order": list(SEEDS)} if args.grid == "wide" else {}),
    )
    abort = False
    next_index = 0
    simulation_futures = {}
    postprocess_futures = {}
    saved_conditions = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.slots) as simulation_pool, \
            concurrent.futures.ThreadPoolExecutor(max_workers=args.cleanup_workers) as cleanup_pool:
        while simulation_futures or next_index < len(queue):
            done = [future for future in simulation_futures if future.done()]
            for future in done:
                simulation_futures.pop(future)
                condition, value, seed, report = future.result()
                context = contexts[(condition, value)]
                context["reports"].append(report)
                if failed(report):
                    abort = True
                    emit(
                        "orchestration_abort_requested",
                        condition=condition,
                        lambda_value=value,
                        seed=seed,
                        error=report.get("error"),
                    )
                if len(context["reports"]) == len(context["seeds"]):
                    finalize_context(condition, value)
                    if context["manifest"]["status"] == "completed":
                        cleanup_future = cleanup_pool.submit(postprocess, condition, value)
                        context["postprocess"] = cleanup_future
                        postprocess_futures[cleanup_future] = (condition, value)

            completed_cleanup = [future for future in postprocess_futures if future.done()]
            for future in completed_cleanup:
                condition, value = postprocess_futures.pop(future)
                try:
                    future.result()
                except Exception as error:
                    abort = True
                    emit(
                        "postprocess_abort_requested",
                        condition=condition,
                        lambda_value=value,
                        error=repr(error),
                    )

            if monitor_state["violation"] is not None:
                abort = True
            capacity = args.slots - len(simulation_futures)
            while not abort and capacity > 0 and next_index < len(queue):
                condition, value, seed = queue[next_index]
                future = simulation_pool.submit(execute, condition, value, seed, next_index)
                simulation_futures[future] = (condition, value, seed)
                emit(
                    "slot_filled",
                    condition=condition,
                    lambda_value=value,
                    seed=seed,
                    queue_index=next_index,
                    managed_active=len(simulation_futures),
                )
                next_index += 1
                capacity -= 1
            if abort and not simulation_futures:
                break
            if simulation_futures:
                concurrent.futures.wait(
                    simulation_futures,
                    timeout=0.25,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
            else:
                time.sleep(0.25)

        for future, (condition, value) in list(postprocess_futures.items()):
            try:
                future.result()
            except Exception as error:
                abort = True
                emit(
                    "postprocess_abort_requested",
                    condition=condition,
                    lambda_value=value,
                    error=repr(error),
                )

    stop_monitor.set()
    monitor_thread.join(timeout=2)
    for condition in args.condition_order:
        condition_contexts = [
            context for (key, _), context in contexts.items() if key == condition
        ]
        if all(
            context["finalized"]
            and context["manifest"]["status"] == "completed"
            and context["postprocess"] is not None
            and context["postprocess"].done()
            and context["postprocess"].exception() is None
            for context in condition_contexts
        ):
            root, branch = supplied[condition]
            saved_conditions[condition] = git_save_condition(
                condition,
                root,
                branch,
                [context["args"].output for context in condition_contexts],
                args.push_results,
            )
            emit(
                "condition_saved",
                condition=condition,
                branch=branch,
                commit=saved_conditions[condition],
            )
        else:
            abort = True

    emit(
        "orchestration_finished",
        submitted_tasks=next_index,
        total_tasks=len(queue),
        max_active_runs=max_active,
        max_machine_sumo_processes=monitor_state["max_sumo"],
        machine_slot_violation=monitor_state["violation"],
        saved_conditions=saved_conditions,
        aborted=abort,
    )
    return 0 if not abort and next_index == len(queue) else 1


if __name__ == "__main__":
    raise SystemExit(main())

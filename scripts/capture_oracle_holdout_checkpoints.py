#!/usr/bin/env python3
"""Capture all exact pre-decision checkpoints in one replay per natural run."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
sys.path.insert(0, str(ROOT / "scripts"))

import mcs_checkpoint  # noqa: E402
from run_decision_oracle import common_env, run_process, scenario_command  # noqa: E402
from run_thesis_batch import (  # noqa: E402
    git_metadata, prepare_source, source_hashes, write_json,
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_events(paths: list[Path]) -> list[dict]:
    events = []
    for path in paths:
        plan = read_json(path)
        if plan.get("schema") != "decision-oracle-plan-v1":
            raise ValueError(f"unsupported plan: {path}")
        if plan.get("event_count") != 120:
            raise ValueError(f"expected 120 events in {path}")
        events.extend(plan["events"])
    if len(events) != 960:
        raise ValueError(f"expected 960 planned events, got {len(events)}")
    identities = {
        (event["case"], event["origin_policy"], int(event["seed"]),
         int(event["ordinal"]))
        for event in events
    }
    if len(identities) != len(events):
        raise ValueError("duplicate event identity across plans")
    return events


def failed_group_manifest(key: tuple, event_count: int, error: Exception,
                          run_git: dict) -> dict:
    case, origin, seed = key
    return {
        "schema": "oracle-holdout-exact-checkpoint-group-v1",
        "status": "failed",
        "case": case, "origin_policy": origin, "seed": seed,
        "event_count": event_count,
        "checkpoint_count": 0,
        "exit_code": -1,
        "exception": f"{type(error).__name__}: {error}",
        "source_unchanged": False,
        "git": run_git,
    }


def run_group(key: tuple, events: list[dict], args, run_git: dict) -> dict:
    case, origin, seed = key
    destination = args.output / case / origin / f"seed-{seed}"
    destination.mkdir(parents=True)
    source, initial_hashes = prepare_source(destination, case)
    checkpoint_times = sorted({
        round(float(event["sim_time_s"]) - 0.1, 1) for event in events
    })
    if checkpoint_times[0] <= 0:
        raise ValueError(f"invalid checkpoint time for {key}")
    replay = SimpleNamespace(
        sumo_home=args.sumo_home,
        python=str(args.python),
        case=case,
        seed=int(seed),
        duration=300.0,
        origin_policy=origin,
        deceleration_loss_lambda=2.0,
    )
    checkpoint_root = destination / "checkpoints"
    env = common_env(replay, source)
    env.update(
        MCS_CHECKPOINT_DIR=str(checkpoint_root),
        MCS_CHECKPOINT_AT=",".join(str(value) for value in checkpoint_times),
        MCS_NEGOTIATION_AUDIT=str(destination / "negotiations.jsonl"),
    )
    command, fixed = scenario_command(
        replay, source, checkpoint_times[-1])
    code, elapsed = run_process(
        command, source / {"eval3": "junction", "eval5": "junction",
                          "eval7": "merge"}[case], env,
        destination / "stdout.log", destination / "stderr.log")
    missing = []
    for moment in checkpoint_times:
        checkpoint = checkpoint_root / mcs_checkpoint.checkpoint_name(moment)
        for name in ("checkpoint.json", "mcs-state.pkl", "sumo-state.xml.gz"):
            if not (checkpoint / name).is_file():
                missing.append(str(checkpoint / name))
    unchanged = source_hashes(source) == initial_hashes
    manifest = {
        "schema": "oracle-holdout-exact-checkpoint-group-v1",
        "status": "completed" if code == 0 and not missing and unchanged else "failed",
        "case": case, "origin_policy": origin, "seed": seed,
        "event_count": len(events),
        "checkpoint_count": len(checkpoint_times),
        "checkpoint_times_s": checkpoint_times,
        "events": events,
        "command": command,
        "fixed_vehicle_input": fixed,
        "exit_code": code,
        "elapsed_seconds": elapsed,
        "missing_checkpoint_files": missing,
        "source_unchanged": unchanged,
        "git": run_git,
    }
    write_json(destination / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="append", type=Path, required=True)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    if len(args.plan) != 8:
        parser.error("exactly eight plan files are required")
    if args.output.exists():
        parser.error("output directory already exists")
    if args.workers != 10:
        parser.error("the preregistered exact capture uses 10 workers")
    args.plan = [path.resolve() for path in args.plan]
    args.sumo_home = args.sumo_home.resolve()
    args.python = args.python.absolute()
    args.output = args.output.resolve()
    try:
        events = load_events(args.plan)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    grouped = {}
    for event in events:
        key = (event["case"], event["origin_policy"], int(event["seed"]))
        grouped.setdefault(key, []).append(event)
    if len(grouped) != 60 or any(len(values) != 16 for values in grouped.values()):
        parser.error("plans must contain 60 case/origin/seed groups of 16 events")
    run_git = git_metadata()
    if run_git.get("dirty") is not False:
        parser.error("formal checkpoint capture requires a clean worktree")
    args.output.mkdir(parents=True)
    started = time.time()
    runner_log = args.output / "runner.log"

    def log(record: dict) -> None:
        with runner_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        print(json.dumps(record), flush=True)

    log({"event": "capture_started", "groups": len(grouped),
         "workers": args.workers})
    manifests = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_group, key, values, args, run_git): key
            for key, values in sorted(grouped.items())
        }
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                manifest = future.result()
            except Exception as error:
                manifest = failed_group_manifest(
                    key, len(grouped[key]), error, run_git)
            manifests.append(manifest)
            log({
                "event": "group_finished",
                "case": manifest["case"],
                "origin_policy": manifest["origin_policy"],
                "seed": manifest["seed"],
                "status": manifest["status"],
                "elapsed_seconds": manifest["elapsed_seconds"],
            })
    failures = [item for item in manifests if item["status"] != "completed"]
    plan_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in args.plan
    }
    manifest = {
        "schema": "oracle-holdout-exact-checkpoint-batch-v1",
        "status": "completed" if not failures else "failed",
        "git": run_git,
        "workers": args.workers,
        "group_count": len(manifests),
        "failed_group_count": len(failures),
        "planned_event_count": len(events),
        # Multiple negotiations can occur at the same 0.1 s instant.  They
        # intentionally share one pre-decision checkpoint, but every planned
        # event must still have a checkpoint reference.
        "event_checkpoint_reference_count": sum(
            item["event_count"] for item in manifests
            if item["status"] == "completed"),
        "checkpoint_count": sum(item["checkpoint_count"] for item in manifests),
        "plan_sha256": plan_hashes,
        "source_unchanged": all(item["source_unchanged"] for item in manifests),
        "elapsed_seconds": time.time() - started,
        "exit_code": 0 if not failures else 1,
    }
    write_json(args.output / "experiment-manifest.json", manifest)
    log({"event": "capture_finished", "status": manifest["status"],
         "elapsed_seconds": manifest["elapsed_seconds"]})
    raise SystemExit(manifest["exit_code"])


if __name__ == "__main__":
    main()

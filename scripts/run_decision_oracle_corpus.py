#!/usr/bin/env python3
"""Execute a preregistered decision-oracle plan with a shared source snapshot."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
sys.path.insert(0, str(ROOT / "scripts"))

import decision_oracle  # noqa: E402
from run_thesis_batch import (  # noqa: E402
    git_metadata, prepare_source, source_hashes, write_json,
)


def validate_checkpoint_batch(root, origin_policy, duration):
    """Validate the natural-run batch that owns reusable checkpoints."""
    if root is None:
        return None
    path = root / "experiment-manifest.json"
    if not path.is_file():
        raise ValueError(f"checkpoint batch manifest does not exist: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    failures = []
    if manifest.get("status") != "completed":
        failures.append(f"status={manifest.get('status')}")
    if manifest.get("completed_simulations") != 30:
        failures.append(
            f"completed_simulations={manifest.get('completed_simulations')}")
    if manifest.get("failed_simulations") != 0:
        failures.append(f"failed_simulations={manifest.get('failed_simulations')}")
    if float(manifest.get("duration_s", -1)) != float(duration):
        failures.append(f"duration_s={manifest.get('duration_s')}")
    if float(manifest.get("checkpoint_interval_s", 0)) <= 0:
        failures.append(
            f"checkpoint_interval_s={manifest.get('checkpoint_interval_s')}")
    method = str(manifest.get("method", ""))
    if origin_policy == "yamashita" and not method.startswith("yamashita"):
        failures.append(f"method={method}")
    if origin_policy == "proposal" and not method.startswith("proposal"):
        failures.append(f"method={method}")
    if failures:
        raise ValueError(
            f"invalid {origin_policy} checkpoint batch {path}: "
            + ", ".join(failures))
    return {"path": str(path), "manifest": manifest}


def event_slug(index, event):
    return (
        f"{index:03d}-{event['case']}-{event['origin_policy']}-"
        f"seed-{event['seed']}-event-{event['ordinal']:04d}")


def event_manifest(output):
    matches = []
    for path in output.rglob("manifest.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema") == "decision-oracle-event-v2":
            matches.append((path, value))
    if len(matches) != 1:
        raise ValueError(f"expected one event manifest in {output}, got {len(matches)}")
    return matches[0]


def capture_checkpoint_for_event(args, event):
    """Choose the latest complete natural-run checkpoint before an event."""
    root = args.checkpoint_roots.get(event["origin_policy"])
    if root is None:
        return None
    run_root = root / event["case"] / f"seed-{event['seed']}"
    run_manifest_path = run_root / "manifest.json"
    if not run_manifest_path.is_file():
        raise ValueError(
            f"checkpoint source run manifest does not exist: {run_manifest_path}")
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    if (run_manifest.get("exit_code") != 0
            or run_manifest.get("source_unchanged") is not True):
        raise ValueError(
            f"checkpoint source run is invalid: {run_manifest_path}; "
            f"exit_code={run_manifest.get('exit_code')}, "
            f"source_unchanged={run_manifest.get('source_unchanged')}")
    checkpoint_root = run_root / "checkpoints"
    if not checkpoint_root.is_dir():
        raise ValueError(f"checkpoint directory does not exist: {checkpoint_root}")
    event_checkpoint_time = round(float(event["sim_time_s"]) - 0.1, 1)
    candidates = []
    for path in checkpoint_root.iterdir():
        metadata_path = path / "checkpoint.json"
        if not path.is_dir() or not metadata_path.is_file():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        required = ("checkpoint.json", "mcs-state.pkl", "sumo-state.xml.gz")
        if not all((path / name).is_file() for name in required):
            continue
        if metadata.get("case") != event["case"]:
            continue
        if int(metadata.get("seed", -1)) != int(event["seed"]):
            continue
        moment = float(metadata.get("simulation_time_s", math.inf))
        if 0 < moment < event_checkpoint_time:
            candidates.append((moment, path))
    return max(candidates, key=lambda item: item[0], default=(None, None))[1]


def run_event(args, source, git_metadata_path, output_root, index, event,
              capture_checkpoint=None):
    slug = event_slug(index, event)
    output = output_root / "events" / slug
    log_dir = output_root / "runner-logs"
    command = [
        str(args.python), str(ROOT / "scripts" / "run_decision_oracle.py"),
        "--sumo-home", str(args.sumo_home),
        "--python", str(args.python),
        "--source", str(source),
        "--git-metadata-json", str(git_metadata_path),
        "--output", str(output),
        "--case", event["case"],
        "--origin-policy", event["origin_policy"],
        "--seed", str(event["seed"]),
        "--duration", str(args.duration),
        "--deceleration-loss-lambda", str(args.deceleration_loss_lambda),
        "--cohort-mode", args.cohort_mode,
        "--event-ordinal", str(event["ordinal"]),
        "--event-time", str(event["sim_time_s"]),
        "--receiver-id", str(event["receiver_id"]),
        "--sender-id", str(event["sender_id"]),
        "--desired-path-id", str(event["desired_path_id"]),
    ]
    if capture_checkpoint is not None:
        command += ["--capture-resume-checkpoint", str(capture_checkpoint)]
    started = time.monotonic()
    with (log_dir / f"{slug}.stdout.log").open("w", encoding="utf-8") as stdout, \
            (log_dir / f"{slug}.stderr.log").open("w", encoding="utf-8") as stderr:
        completed = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr)
    result = {
        "index": index, "slug": slug, "event": event, "command": command,
        "exit_code": completed.returncode,
        "elapsed_seconds": time.monotonic() - started,
        "capture_resume_checkpoint": (str(capture_checkpoint)
                                      if capture_checkpoint is not None else None),
    }
    if completed.returncode == 0:
        path, manifest = event_manifest(output)
        result["event_manifest"] = str(path.relative_to(output_root))
        result["manifest"] = manifest
    return result


def grouped_summary(events, key):
    groups = {}
    for event in events:
        name = key(event["event"])
        groups.setdefault(name, []).append(event)
    return {name: decision_oracle.summarize(values)
            for name, values in sorted(groups.items())}


def macro_case_mean_regret(case_summaries):
    policies = sorted({
        policy for summary in case_summaries.values()
        for policy in summary.get("policies", {})
    })
    output = {}
    for policy in policies:
        values = [
            case_summaries[case].get("policies", {}).get(policy, {}).get(
                "mean_regret_m")
            for case in ("eval3", "eval5", "eval7")
        ]
        output[policy] = (sum(values) / len(values)
                          if all(value is not None for value in values)
                          else None)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument(
        "--deceleration-loss-lambda", type=float, default=1.0,
        help="proposal-origin loss weight used by the discovery batch")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument(
        "--cohort-mode", choices=("all-observed", "actors-followers"),
        default="all-observed")
    parser.add_argument(
        "--checkpoint-root-yamashita", type=Path,
        help="natural-run batch root containing case/seed/checkpoints")
    parser.add_argument(
        "--checkpoint-root-proposal", type=Path,
        help="natural-run batch root containing case/seed/checkpoints")
    args = parser.parse_args()
    args.plan = args.plan.resolve()
    args.sumo_home = args.sumo_home.resolve()
    # Preserve virtualenv interpreter symlinks while making the child command
    # independent of its working directory.
    args.python = args.python.absolute()
    args.output = args.output.resolve()
    if ((args.checkpoint_root_yamashita is None)
            != (args.checkpoint_root_proposal is None)):
        parser.error("both natural-run checkpoint roots must be supplied together")
    args.checkpoint_roots = {
        "yamashita": (args.checkpoint_root_yamashita.resolve()
                      if args.checkpoint_root_yamashita is not None else None),
        "proposal": (args.checkpoint_root_proposal.resolve()
                     if args.checkpoint_root_proposal is not None else None),
    }
    if args.output.exists():
        parser.error("output directory already exists")
    if args.workers < 1:
        parser.error("workers must be positive")
    if (not math.isfinite(args.deceleration_loss_lambda) or
            args.deceleration_loss_lambda < 0):
        parser.error("--deceleration-loss-lambda must be finite and non-negative")
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    if plan.get("schema") != "decision-oracle-plan-v1":
        parser.error("unsupported plan schema")
    if plan.get("event_count") != 120 or len(plan.get("events", ())) != 120:
        parser.error("the preregistered plan must contain exactly 120 events")
    try:
        checkpoint_batches = {
            name: validate_checkpoint_batch(root, name, args.duration)
            for name, root in args.checkpoint_roots.items()
        }
        capture_checkpoints = [
            capture_checkpoint_for_event(args, event)
            for event in plan["events"]
        ]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    run_git = git_metadata()
    if run_git.get("dirty") is not False:
        parser.error("formal corpus requires a clean worktree at startup")
    args.output.mkdir(parents=True)
    (args.output / "events").mkdir()
    (args.output / "runner-logs").mkdir()
    (args.output / "plan.json").write_bytes(plan_bytes)
    git_metadata_path = args.output / "run-git-metadata.json"
    write_json(git_metadata_path, run_git)
    source, initial_hashes = prepare_source(args.output, "eval3")
    started = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(
                run_event, args, source, git_metadata_path,
                args.output, index, event, capture_checkpoint)
            for index, (event, capture_checkpoint) in enumerate(
                zip(plan["events"], capture_checkpoints), 1)
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["index"])
    completed_events = [result["manifest"] for result in results
                        if result.get("manifest") is not None]
    failures = [{key: value for key, value in result.items() if key != "manifest"}
                for result in results if result.get("exit_code") != 0]
    case_summaries = grouped_summary(completed_events, lambda event: event["case"])
    origin_summaries = grouped_summary(
        completed_events, lambda event: event["origin_policy"])
    case_origin_summaries = grouped_summary(
        completed_events,
        lambda event: f"{event['case']}:{event['origin_policy']}")
    unchanged = source_hashes(source) == initial_hashes
    status = ("completed" if not failures and len(completed_events) == 120
              and unchanged else "incomplete")
    manifest = {
        "schema": "decision-oracle-corpus-v1",
        "status": status,
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "planned_event_count": 120,
        "completed_event_count": len(completed_events),
        "failed_event_count": len(failures),
        "failures": failures,
        "source_unchanged": unchanged,
        "git": run_git,
        "python": str(args.python),
        "sumo_home": str(args.sumo_home),
        "duration_s": args.duration,
        "deceleration_loss_lambda": args.deceleration_loss_lambda,
        "cohort_mode": args.cohort_mode,
        "workers": args.workers,
        "capture_checkpoint_roots": {
            name: (str(path) if path is not None else None)
            for name, path in args.checkpoint_roots.items()
        },
        "capture_checkpoint_batches": checkpoint_batches,
        "capture_resume_event_count": sum(
            checkpoint is not None for checkpoint in capture_checkpoints),
        "started_epoch": started,
        "ended_epoch": time.time(),
        "overall": decision_oracle.summarize(completed_events),
        "by_case": case_summaries,
        "by_origin": origin_summaries,
        "by_case_origin": case_origin_summaries,
        "primary_macro_case_mean_regret_m": macro_case_mean_regret(
            case_summaries),
        "event_results": [
            {key: value for key, value in result.items() if key != "manifest"}
            for result in results
        ],
    }
    write_json(args.output / "manifest.json", manifest)
    print(json.dumps({
        "status": status,
        "completed_event_count": len(completed_events),
        "failed_event_count": len(failures),
        "primary_macro_case_mean_regret_m": manifest[
            "primary_macro_case_mean_regret_m"],
    }, indent=2, allow_nan=False))
    raise SystemExit(0 if status == "completed" else 1)


if __name__ == "__main__":
    main()

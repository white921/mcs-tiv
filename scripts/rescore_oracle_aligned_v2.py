#!/usr/bin/env python3
"""Rescore the saved time-stratified oracle corpus with predictor v2.

The expensive Accept/Reject 10-second branches are immutable evidence and are
not rerun.  For each event this script restores its saved t-0.1 checkpoint,
advances only to the decision boundary with the current source, records the v2
prediction, and scores that prediction against the saved realised branches.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
sys.path.insert(0, str(ROOT / "scripts"))

import decision_oracle  # noqa: E402
from analyze_time_stratified_decision_oracle import (  # noqa: E402
    comparison,
    policy_summary,
)
from run_decision_oracle import (  # noqa: E402
    branch_samples,
    common_env,
    run_process,
    scenario_command,
    validate_event_identity,
)
from run_thesis_batch import git_metadata, source_hashes, write_json  # noqa: E402


POLICIES = (
    "arrival_only",
    "oracle_aligned_v2",
    "proposal_lambda_2",
    "yamashita",
)
BOOTSTRAP_REPETITIONS = 100_000
BOOTSTRAP_SEED = 20261105


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def window_for(moment: float) -> str:
    if 0 <= moment < 100:
        return "0-100"
    if 100 <= moment < 160:
        return "100-160"
    if 160 <= moment < 220:
        return "160-220"
    if 220 <= moment <= 290:
        return "220-290"
    raise ValueError(f"event time is outside the fixed windows: {moment}")


def discover_events(results_root: Path) -> list[Path]:
    paths = sorted(results_root.glob(
        "follower-impact-time-stratified-*/events/*/*/manifest.json"))
    selected = []
    for path in paths:
        manifest = read_json(path)
        if manifest.get("schema") == "decision-oracle-event-v2":
            selected.append(path)
    return selected


def one_checkpoint(event_dir: Path) -> Path:
    checkpoints = sorted((event_dir / "capture" / "checkpoints").glob("t*"))
    if len(checkpoints) != 1:
        raise ValueError(
            f"expected one saved event checkpoint under {event_dir}, "
            f"got {len(checkpoints)}")
    required = ("checkpoint.json", "mcs-state.pkl", "sumo-state.xml.gz")
    missing = [name for name in required if not (checkpoints[0] / name).is_file()]
    if missing:
        raise ValueError(f"incomplete checkpoint {checkpoints[0]}: {missing}")
    return checkpoints[0]


def run_event(index: int, old_path: Path, args) -> dict:
    old = read_json(old_path)
    event = old["event"]
    event_dir = old_path.parent
    destination = args.output / "events" / (
        f"{index:04d}-{event['case']}-{event['origin_policy']}-"
        f"seed-{event['seed']}-event-{event['ordinal']:04d}")
    destination.mkdir(parents=True)
    checkpoint = one_checkpoint(event_dir)
    replay = SimpleNamespace(
        sumo_home=args.sumo_home,
        python=args.python,
        case=event["case"],
        seed=int(event["seed"]),
        duration=300.0,
        origin_policy=event["origin_policy"],
        deceleration_loss_lambda=2.0,
    )
    boundary_path = destination / "boundary.json"
    old_fingerprint = old["boundary_fingerprint"]
    env = common_env(replay, args.source)
    env.update(
        MCS_ORACLE_TARGET_EVENT=str(event["ordinal"]),
        MCS_ORACLE_FORCE_DECISION="accept",
        MCS_ORACLE_EXPECTED_FINGERPRINT=old_fingerprint,
        MCS_ORACLE_BOUNDARY_AUDIT=str(boundary_path),
        # Proposal-origin checkpoints were created by the old lambda=2 active
        # rule.  Reproduce that lifecycle until the fixed boundary while the
        # boundary's separate proposal_evaluation records v2 in shadow.
        MCS_DECELERATION_REPLAY_LEGACY_ACTIVE="1",
    )
    # A few restored Eval.7 states report the target one floating-point step
    # after an equal-valued --stop-time comparison.  Allow two extra simulator
    # ticks; the audited target boundary is still fixed by ordinal, identity,
    # and fingerprint, and no post-boundary state enters the rescore.
    stop_time = round(float(event["sim_time_s"]) + 0.2, 1)
    command, _ = scenario_command(
        replay, args.source, stop_time, checkpoint)
    code, elapsed = run_process(
        command, args.source / {
            "eval3": "junction", "eval5": "junction", "eval7": "merge",
        }[event["case"]], env,
        destination / "stdout.log", destination / "stderr.log")
    if code != 0 or not boundary_path.is_file():
        raise RuntimeError(f"boundary replay failed for {old_path}; exit={code}")
    boundary = read_json(boundary_path)
    if boundary.get("fingerprint") != old_fingerprint:
        raise RuntimeError(f"boundary fingerprint changed for {old_path}")
    validate_event_identity(boundary["request"], {
        "receiver_id": event["receiver_id"],
        "sender_id": event["sender_id"],
        "desired_path_id": event["desired_path_id"],
    })
    evaluation = boundary.get("proposal_evaluation")
    actor_ids = {
        str(boundary["request"]["sender"]),
        str(boundary["request"]["receiver"]),
    }
    if evaluation is None:
        # The fixed corpus deliberately retains negotiations for which no
        # physical alternative path existed.  They are valid benchmark events
        # but neither the old proposal nor v2 can be scored on them.
        follower_ids = set(map(str, old.get("follower_vehicle_ids", ())))
        cohort = set(map(str, old.get("cohort_vehicle_ids", ())))
        accept = dict(old["branches"]["accept"]["metrics"])
        reject = dict(old["branches"]["reject"]["metrics"])
    else:
        if evaluation.get("decision_rule") not in (
                "oracle-aligned-direct-distance-v2",
                "oracle-aligned-reject-gated-v2"):
            raise RuntimeError(f"unexpected proposal evaluation for {old_path}")
        follower_ids = set(map(str, evaluation.get("union_follower_ids", ())))
        cohort = actor_ids | follower_ids
        start = float(event["sim_time_s"])
        end = round(start + 10.0, 1)
        accept = decision_oracle.realised_metrics(
            branch_samples(
                event_dir / "accept" / "vehicle-states.jsonl", start, end),
            cohort)
        reject = decision_oracle.realised_metrics(
            branch_samples(
                event_dir / "reject" / "vehicle-states.jsonl", start, end),
            cohort)
        accept["safety"] = old["branches"]["accept"]["safety"]
        reject["safety"] = old["branches"]["reject"]["safety"]
    oracle = decision_oracle.oracle_choice(accept, reject)
    choices = decision_oracle.policy_choices(
        boundary.get("yamashita_choice"), evaluation)
    scores = {
        name: decision_oracle.score_policy(choice, accept, reject, oracle)
        for name, choice in choices.items()
    }
    manifest = {
        "schema": "decision-oracle-v2-rescore-event-v1",
        "event": event,
        "source_event_manifest": str(old_path),
        "source_checkpoint": str(checkpoint),
        "boundary_fingerprint": old_fingerprint,
        "boundary_fingerprint_match": True,
        "command": command,
        "exit_code": code,
        "elapsed_seconds": elapsed,
        "proposal_evaluation": evaluation,
        "origin_replay_decision_rule": (
            "legacy-time-equivalent-lambda-2"
            if event["origin_policy"] == "proposal" else "yamashita"),
        "actor_vehicle_ids": sorted(actor_ids),
        "follower_vehicle_ids": sorted(follower_ids),
        "cohort_vehicle_ids": sorted(cohort),
        "branches": {"accept": accept, "reject": reject},
        "oracle": oracle,
        "policy_choices": choices,
        "policy_scores": scores,
    }
    write_json(destination / "manifest.json", manifest)
    return manifest


def event_row(manifest: dict) -> dict:
    event = manifest["event"]
    evaluation = manifest.get("proposal_evaluation") or {}
    row = {
        "case": event["case"],
        "window": window_for(float(event["sim_time_s"])),
        "origin_policy": event["origin_policy"],
        "seed": int(event["seed"]),
        "ordinal": int(event["ordinal"]),
        "sim_time_s": float(event["sim_time_s"]),
        "oracle_choice": manifest["oracle"]["choice"],
        "actual_accept_minus_reject_m": manifest["oracle"][
            "accept_minus_reject_distance_m"],
        "predicted_accept_minus_reject_m": evaluation.get(
            "direct_accept_minus_reject_m"),
        "follower_count": evaluation.get("follower_count"),
        "v2_decision_basis": evaluation.get("decision_basis"),
    }
    for policy in POLICIES:
        score = manifest["policy_scores"].get(policy, {})
        row[f"{policy}_choice"] = manifest["policy_choices"].get(policy)
        row[f"{policy}_correct"] = score.get("correct")
        row[f"{policy}_regret_m"] = (
            score.get("regret_m") if score.get("scored") else None)
    return row


def pearson(rows: list[dict]) -> float | None:
    pairs = [
        (row["predicted_accept_minus_reject_m"],
         row["actual_accept_minus_reject_m"])
        for row in rows
        if row["predicted_accept_minus_reject_m"] is not None
        and row["actual_accept_minus_reject_m"] is not None
        and math.isfinite(row["predicted_accept_minus_reject_m"])
        and math.isfinite(row["actual_accept_minus_reject_m"])
    ]
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in xs)
        * sum((y - mean_y) ** 2 for y in ys))
    return numerator / denominator if denominator else None


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def log(path: Path, message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    args.sumo_home = args.sumo_home.resolve()
    args.source = args.source.resolve()
    args.results_root = args.results_root.resolve()
    args.output = args.output.resolve()
    args.python = str(Path(args.python).absolute())
    if args.output.exists():
        parser.error("output directory already exists")
    if args.workers < 1:
        parser.error("--workers must be positive")

    paths = discover_events(args.results_root)
    if len(paths) != 960:
        parser.error(f"expected 960 saved events, found {len(paths)}")
    args.output.mkdir(parents=True)
    (args.output / "events").mkdir()
    runner_log = args.output / "runner.log"
    initial_hashes = source_hashes(args.source)
    metadata = git_metadata()
    started = time.monotonic()
    log(runner_log, f"start events={len(paths)} workers={args.workers}")
    manifests = []
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_event, index, path, args): path
            for index, path in enumerate(paths, 1)
        }
        for completed, future in enumerate(as_completed(futures), 1):
            try:
                manifests.append(future.result())
            except Exception as error:  # keep the full batch audit visible
                failures.append({
                    "event_manifest": str(futures[future]),
                    "error": f"{type(error).__name__}: {error}",
                })
            if completed % 25 == 0 or completed == len(futures):
                log(runner_log,
                    f"progress completed={completed}/{len(futures)} "
                    f"failed={len(failures)}")

    rows = sorted((event_row(item) for item in manifests), key=lambda row: (
        row["case"], row["origin_policy"], row["seed"],
        row["sim_time_s"], row["ordinal"]))
    write_csv(args.output / "events.csv", rows)
    summary = {
        "events_expected": len(paths),
        "events_completed": len(manifests),
        "events_failed": len(failures),
        "failures": failures,
        "predicted_vs_actual_pearson": pearson(rows),
        "policies": {
            policy: policy_summary(rows, policy) for policy in POLICIES
        },
    }
    if not failures:
        summary["v2_vs_arrival_only"] = comparison(
            rows, "arrival_only", "oracle_aligned_v2",
            BOOTSTRAP_REPETITIONS, BOOTSTRAP_SEED)
        summary["v2_vs_yamashita"] = comparison(
            rows, "yamashita", "oracle_aligned_v2",
            BOOTSTRAP_REPETITIONS, BOOTSTRAP_SEED)
    write_json(args.output / "summary.json", summary)
    source_unchanged = source_hashes(args.source) == initial_hashes
    experiment = {
        "schema": "decision-oracle-v2-rescore-experiment-v1",
        "status": "completed" if not failures and source_unchanged else "failed",
        "development_only": True,
        "reason": "the 960 oracle outcomes were inspected before v2 design",
        "git": metadata,
        "workers": args.workers,
        "results_root": str(args.results_root),
        "event_count": len(manifests),
        "failed_event_count": len(failures),
        "source_unchanged": source_unchanged,
        "elapsed_seconds": time.monotonic() - started,
        "exit_code": 0 if not failures and source_unchanged else 1,
    }
    write_json(args.output / "experiment-manifest.json", experiment)
    log(runner_log, f"finish status={experiment['status']} "
        f"elapsed={experiment['elapsed_seconds']:.1f}s")
    if experiment["exit_code"]:
        raise SystemExit(experiment["exit_code"])


if __name__ == "__main__":
    main()

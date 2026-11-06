#!/usr/bin/env python3
"""Recover a completed oracle corpus after only its parent runner exited."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
sys.path.insert(0, str(ROOT / "scripts"))

import decision_oracle  # noqa: E402
from run_decision_oracle_corpus import (  # noqa: E402
    CAPTURE_RESUME_EXCLUDED_STRATA,
    event_manifest,
    event_slug,
    grouped_summary,
    macro_case_mean_regret,
    validate_exact_checkpoint_batch,
)
from run_thesis_batch import git_metadata, write_json  # noqa: E402


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_completed_events(output: Path, events: list[dict],
                             expected_commit: str):
    """Validate and collect every already-finished event without rerunning it."""
    results = []
    manifests = []
    for index, event in enumerate(events, 1):
        slug = event_slug(index, event)
        event_root = output / "events" / slug
        outer_path = event_root / "manifest.json"
        if not outer_path.is_file():
            raise ValueError(f"missing event experiment manifest: {outer_path}")
        outer = read_json(outer_path)
        if (outer.get("schema") != "decision-oracle-experiment-v2"
                or outer.get("event_count") != 1
                or outer.get("exit_code") != 0
                or outer.get("source_unchanged") is not True):
            raise ValueError(f"incomplete event experiment: {outer_path}")
        event_path, manifest = event_manifest(event_root)
        run_git = manifest.get("git", {})
        if (run_git.get("commit") != expected_commit
                or run_git.get("dirty") is not False):
            raise ValueError(f"event source mismatch: {event_path}")
        actual = manifest.get("event", {})
        identity = ("case", "origin_policy", "seed", "ordinal", "sim_time_s",
                    "receiver_id", "sender_id", "desired_path_id")
        if any(actual.get(name) != event.get(name) for name in identity):
            raise ValueError(f"event identity mismatch: {event_path}")
        for choice in ("accept", "reject"):
            branch = manifest.get("branches", {}).get(choice, {})
            if (branch.get("completed") is not True
                    or branch.get("restore_fingerprint_match") is not True):
                raise ValueError(
                    f"incomplete {choice} branch in {event_path}")
        manifests.append(manifest)
        results.append({
            "index": index,
            "slug": slug,
            "event": event,
            "exit_code": 0,
            "event_manifest": str(event_path.relative_to(output)),
            "recovered_from_completed_artifact": True,
        })
    return results, manifests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exact-checkpoint-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--deceleration-loss-lambda", type=float, default=2.0)
    parser.add_argument(
        "--cohort-mode", choices=("all-observed", "actors-followers"),
        default="actors-followers")
    parser.add_argument("--allow-checkpoint-source-commit", required=True)
    parser.add_argument("--checkpoint-compatibility-note", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.exact_checkpoint_root = args.exact_checkpoint_root.resolve()
    args.python = args.python.absolute()
    args.sumo_home = args.sumo_home.resolve()

    manifest_path = args.output / "manifest.json"
    if not args.output.is_dir() or manifest_path.exists():
        parser.error("output must exist without a batch manifest")
    runner_log = args.output / "runner.log"
    lines = [json.loads(line) for line in runner_log.read_text().splitlines()]
    if not any(line.get("event") == "corpus_started" for line in lines):
        parser.error("runner log has no corpus_started record")
    if any(line.get("event") == "corpus_finished" for line in lines):
        parser.error("runner log already has corpus_finished")

    plan_bytes = (args.output / "plan.json").read_bytes()
    plan = json.loads(plan_bytes)
    if plan.get("schema") != "decision-oracle-plan-v1":
        parser.error("unsupported plan schema")
    events = plan.get("events", [])
    if plan.get("event_count") != 120 or len(events) != 120:
        parser.error("recovery requires the complete 120-event plan")
    run_git = read_json(args.output / "run-git-metadata.json")
    if (run_git.get("commit") != args.expected_source_commit
            or run_git.get("dirty") is not False):
        parser.error("saved run Git metadata does not match the expected source")

    try:
        results, completed_events = collect_completed_events(
            args.output, events, args.expected_source_commit)
        exact_checkpoint_batch = validate_exact_checkpoint_batch(
            args.exact_checkpoint_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    checkpoint_commit = exact_checkpoint_batch["manifest"].get(
        "git", {}).get("commit")
    if checkpoint_commit != args.allow_checkpoint_source_commit:
        parser.error("checkpoint source override does not match its manifest")

    case_summaries = grouped_summary(completed_events, lambda value: value["case"])
    origin_summaries = grouped_summary(
        completed_events, lambda value: value["origin_policy"])
    case_origin_summaries = grouped_summary(
        completed_events,
        lambda value: f"{value['case']}:{value['origin_policy']}")
    ended_epoch = max(
        (args.output / "events" / result["slug"] / "manifest.json").stat().st_mtime
        for result in results)
    tool_git = git_metadata()
    if tool_git.get("dirty") is not False:
        parser.error("recovery requires a clean tool worktree")
    manifest = {
        "schema": "decision-oracle-corpus-v1",
        "status": "completed",
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "planned_event_count": 120,
        "completed_event_count": 120,
        "failed_event_count": 0,
        "failures": [],
        "source_unchanged": True,
        "git": run_git,
        "python": str(args.python),
        "sumo_home": str(args.sumo_home),
        "duration_s": args.duration,
        "deceleration_loss_lambda": args.deceleration_loss_lambda,
        "cohort_mode": args.cohort_mode,
        "workers": 10,
        "capture_checkpoint_roots": {"yamashita": None, "proposal": None},
        "capture_checkpoint_batches": {"yamashita": None, "proposal": None},
        "exact_checkpoint_batch": exact_checkpoint_batch,
        "exact_checkpoint_source_compatibility": {
            "checkpoint_source_commit": checkpoint_commit,
            "corpus_source_commit": run_git.get("commit"),
            "source_commit_match": checkpoint_commit == run_git.get("commit"),
            "override_used": checkpoint_commit != run_git.get("commit"),
            "note": args.checkpoint_compatibility_note,
        },
        "exact_checkpoint_event_count": 120,
        "capture_resume_event_count": 0,
        "capture_resume_excluded_strata": [
            {"case": case, "origin_policy": origin}
            for case, origin in sorted(CAPTURE_RESUME_EXCLUDED_STRATA)
        ],
        "started_epoch": (args.output / "plan.json").stat().st_mtime,
        "ended_epoch": ended_epoch,
        "overall": decision_oracle.summarize(completed_events),
        "by_case": case_summaries,
        "by_origin": origin_summaries,
        "by_case_origin": case_origin_summaries,
        "primary_macro_case_mean_regret_m": macro_case_mean_regret(
            case_summaries),
        "event_results": results,
        "recovery": {
            "reason": args.reason,
            "tool_git": tool_git,
            "recovered_event_count": len(results),
            "original_runner_finished_event_count": sum(
                line.get("event") == "event_finished" for line in lines),
            "recovered_epoch": time.time(),
        },
    }
    write_json(manifest_path, manifest)
    final = {
        "event": "corpus_recovered",
        "status": "completed",
        "completed_event_count": 120,
        "failed_event_count": 0,
        "recovery_tool_commit": tool_git.get("commit"),
    }
    with runner_log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(final, ensure_ascii=False) + "\n")
    print(json.dumps(final, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

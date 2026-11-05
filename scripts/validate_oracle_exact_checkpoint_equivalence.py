#!/usr/bin/env python3
"""Compare from-start and grouped exact-checkpoint oracle events in six strata."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_thesis_batch import git_metadata, write_json  # noqa: E402


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_events(plan_dir: Path) -> list[dict]:
    events = []
    for path in sorted(plan_dir.glob("oracle-v2-*.json")):
        plan = read_json(path)
        events.extend(plan["events"])
    selected = []
    for case in ("eval3", "eval5", "eval7"):
        for origin in ("yamashita", "proposal"):
            candidates = [event for event in events
                          if event["case"] == case
                          and event["origin_policy"] == origin]
            selected.append(min(candidates, key=lambda event: (
                float(event["sim_time_s"]), int(event["seed"]),
                int(event["ordinal"]))))
    return selected


def exact_checkpoint(root: Path, event: dict) -> Path:
    moment = round(float(event["sim_time_s"]) - 0.1, 1)
    return (root / event["case"] / event["origin_policy"]
            / f"seed-{event['seed']}" / "checkpoints"
            / f"t{moment:09.1f}")


def event_manifest(root: Path) -> dict:
    found = []
    for path in root.rglob("manifest.json"):
        value = read_json(path)
        if value.get("schema") == "decision-oracle-event-v2":
            found.append(value)
    if len(found) != 1:
        raise ValueError(f"expected one event manifest in {root}, got {len(found)}")
    return found[0]


def compare(reference: dict, exact: dict) -> dict:
    differences = []
    fingerprint_match = (
        reference["boundary_fingerprint"] == exact["boundary_fingerprint"])
    if not fingerprint_match:
        differences.append("boundary_fingerprint")
    exact_fields = (
        "event", "policy_choices", "actor_vehicle_ids", "follower_vehicle_ids",
        "cohort_vehicle_ids",
    )
    for field in exact_fields:
        if reference.get(field) != exact.get(field):
            differences.append(field)
    for field in ("choice", "valid"):
        if reference["oracle"].get(field) != exact["oracle"].get(field):
            differences.append("oracle." + field)
    numeric = []
    for branch in ("accept", "reject"):
        for field in ("distance_m", "hard_brake_time_s", "stop_time_s"):
            left = float(reference["branches"][branch]["metrics"][field])
            right = float(exact["branches"][branch]["metrics"][field])
            delta = right - left
            numeric.append({"field": f"{branch}.{field}", "difference": delta})
            if not math.isclose(left, right, rel_tol=0, abs_tol=1e-6):
                differences.append(f"{branch}.{field}")
        if reference["branches"][branch]["safety"] != exact["branches"][branch]["safety"]:
            differences.append(f"{branch}.safety")
    return {
        "equivalent": not differences,
        "differences": differences,
        "numeric_differences": numeric,
        "cross_process_boundary_fingerprint_match": fingerprint_match,
    }


def run_event(event: dict, args) -> dict:
    slug = (f"{event['case']}-{event['origin_policy']}-seed-{event['seed']}-"
            f"event-{int(event['ordinal']):04d}")
    common = [
        str(args.python), str(ROOT / "scripts" / "run_decision_oracle.py"),
        "--sumo-home", str(args.sumo_home), "--python", str(args.python),
        "--case", event["case"], "--origin-policy", event["origin_policy"],
        "--seed", str(event["seed"]), "--duration", "300",
        "--deceleration-loss-lambda", "2", "--cohort-mode", "actors-followers",
        "--event-ordinal", str(event["ordinal"]),
        "--event-time", str(event["sim_time_s"]),
        "--receiver-id", str(event["receiver_id"]),
        "--sender-id", str(event["sender_id"]),
        "--desired-path-id", str(event["desired_path_id"]),
    ]
    reference_root = args.output / (slug + "-from-start")
    exact_root = args.output / (slug + "-exact")
    started = time.monotonic()
    reference = subprocess.run(
        common + ["--output", str(reference_root)], cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    exact = subprocess.run(
        common + ["--output", str(exact_root), "--exact-checkpoint",
                  str(exact_checkpoint(args.exact_checkpoint_root, event))],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if reference.returncode or exact.returncode:
        return {
            "event": event, "reference_exit_code": reference.returncode,
            "exact_exit_code": exact.returncode, "equivalent": False,
            "elapsed_seconds": time.monotonic() - started,
        }
    result = compare(event_manifest(reference_root), event_manifest(exact_root))
    return {
        "event": event, "reference_exit_code": 0, "exact_exit_code": 0,
        **result, "elapsed_seconds": time.monotonic() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--exact-checkpoint-root", type=Path, required=True)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    args.plan_dir = args.plan_dir.resolve()
    args.exact_checkpoint_root = args.exact_checkpoint_root.resolve()
    args.sumo_home = args.sumo_home.resolve()
    args.python = args.python.absolute()
    args.output = args.output.resolve()
    if args.output.exists():
        parser.error("output directory already exists")
    if args.workers < 1 or args.workers > 6:
        parser.error("workers must be between 1 and 6")
    events = selected_events(args.plan_dir)
    if len(events) != 6:
        parser.error("expected six case/origin smoke events")
    run_git = git_metadata()
    if run_git.get("dirty") is not False:
        parser.error("equivalence validation requires a clean worktree")
    capture_manifest = read_json(
        args.exact_checkpoint_root / "experiment-manifest.json")
    if (capture_manifest.get("status") != "completed"
            or capture_manifest.get("git", {}).get("commit") != run_git.get("commit")):
        parser.error("exact checkpoint batch is incomplete or from another source")
    args.output.mkdir(parents=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda event: run_event(event, args), events))
    passed = all(result.get("equivalent") is True for result in results)
    manifest = {
        "schema": "oracle-exact-checkpoint-equivalence-v1",
        "status": "passed" if passed else "failed",
        "git": run_git,
        "events": results,
        "event_count": len(results),
        "equivalent_event_count": sum(
            result.get("equivalent") is True for result in results),
        "exit_code": 0 if passed else 1,
    }
    write_json(args.output / "experiment-manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    raise SystemExit(manifest["exit_code"])


if __name__ == "__main__":
    main()

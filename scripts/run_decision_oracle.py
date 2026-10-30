#!/usr/bin/env python3
"""Run one audited Eval.3 Accept/Reject counterfactual event.

The branch pair restores the same checkpoint from the simulator step directly
before the decision.  Each replay must reproduce an identical pre-decision
fingerprint before the target choice alone is forced.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
sys.path.insert(0, str(ROOT / "scripts"))

import decision_oracle  # noqa: E402
import mcs_checkpoint  # noqa: E402
from run_thesis_batch import (  # noqa: E402
    CASES, clean_experiment_environment, fixed_input_details, git_metadata,
    prepare_source, source_hashes, write_json,
)


def read_jsonl(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def branch_samples(path, start_s, end_s):
    samples = {}
    for frame in read_jsonl(path):
        moment = float(frame.get("sim_time", -1))
        if not start_s < moment <= end_s + 1e-6:
            continue
        for vehicle in frame.get("vehicles", ()):
            reference = vehicle.get("allowed_speed_mps")
            if reference is None:
                continue
            samples.setdefault(str(vehicle["vehicle_id"]), []).append({
                "speed_mps": vehicle["speed_mps"],
                "reference_speed_mps": reference,
                "accel_mps2": vehicle.get("accel_mps2", 0.0),
            })
    return samples


def run_process(command, cwd, env, stdout_path, stderr_path):
    started = time.monotonic()
    with stdout_path.open("w", encoding="utf-8") as stdout, \
            stderr_path.open("w", encoding="utf-8") as stderr:
        completed = subprocess.run(command, cwd=cwd, env=env,
                                   stdout=stdout, stderr=stderr)
    return completed.returncode, time.monotonic() - started


def common_env(args, source):
    sumo_home = args.sumo_home.resolve()
    return dict(
        clean_experiment_environment(),
        SUMO_HOME=str(sumo_home),
        PYTHONPATH=str(sumo_home / "tools"),
        MPLBACKEND="Agg", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
        MCS_TIV_IMPLEMENTATION="thesis", MCS_DECELERATION_MODE="off",
    )


def scenario_command(args, source, stop_time, resume=None):
    case = CASES["eval3"]
    fixed = fixed_input_details(
        "eval3", args.seed, args.duration, "fixed",
        prefix_duration=args.duration, source_root=source)
    command = [
        args.python, "-u", case["script"], case["alpha"], str(args.seed),
        *case["flows"], "--nogui", "--quiet", "--no-save",
        "--duration", str(args.duration), "--stop-time", str(stop_time),
        "--bus-allocation", "fixed", "--fixed-input", fixed["runtime_path"],
    ]
    if resume is not None:
        command += ["--resume-checkpoint", str(resume)]
    return command, fixed


def run_capture(args, event, source, event_dir, initial_hashes):
    capture_dir = event_dir / "capture"
    capture_dir.mkdir()
    checkpoint_time = round(float(args.event_time) - 0.1, 1)
    if checkpoint_time <= 0:
        raise ValueError("event time must be later than 0.1 s")
    env = common_env(args, source)
    env.update(
        MCS_CHECKPOINT_DIR=str(capture_dir / "checkpoints"),
        MCS_CHECKPOINT_AT=str(checkpoint_time),
        MCS_NEGOTIATION_AUDIT=str(capture_dir / "negotiations.jsonl"),
    )
    command, fixed = scenario_command(args, source, checkpoint_time)
    code, elapsed = run_process(
        command, source / "junction", env,
        capture_dir / "stdout.log", capture_dir / "stderr.log")
    checkpoint = capture_dir / "checkpoints" / mcs_checkpoint.checkpoint_name(checkpoint_time)
    manifest = {
        "record_type": "decision-oracle-capture", "event": event,
        "command": command, "exit_code": code, "elapsed_seconds": elapsed,
        "checkpoint_time_s": checkpoint_time,
        "checkpoint": str(checkpoint),
        "checkpoint_complete": all((checkpoint / name).is_file() for name in (
            "checkpoint.json", "mcs-state.pkl", "sumo-state.xml.gz")),
        "source_unchanged": source_hashes(source) == initial_hashes,
        "fixed_vehicle_input": fixed,
    }
    write_json(capture_dir / "manifest.json", manifest)
    if code != 0 or not manifest["checkpoint_complete"] or not manifest["source_unchanged"]:
        raise RuntimeError("capture did not complete with an unchanged source")
    return checkpoint


def run_branch(args, event, source, event_dir, initial_hashes, checkpoint,
               choice, expected_fingerprint=None):
    destination = event_dir / choice
    destination.mkdir()
    end_time = round(float(args.event_time) + 10.0, 1)
    env = common_env(args, source)
    env.update(
        MCS_ORACLE_TARGET_EVENT=str(args.event_ordinal),
        MCS_ORACLE_FORCE_DECISION=choice,
        MCS_ORACLE_BOUNDARY_AUDIT=str(destination / "boundary.json"),
        MCS_VEHICLE_STATE_AUDIT=str(destination / "vehicle-states.jsonl"),
        MCS_NEGOTIATION_AUDIT=str(destination / "negotiations.jsonl"),
        MCS_PHYSICAL_COLLISION_AUDIT=str(destination / "physical-collisions.jsonl"),
        MCS_EVALUATION_AUDIT=str(destination / "evaluation-metrics.json"),
    )
    if expected_fingerprint is not None:
        env["MCS_ORACLE_EXPECTED_FINGERPRINT"] = expected_fingerprint
    command, _ = scenario_command(args, source, end_time, checkpoint)
    code, elapsed = run_process(
        command, source / "junction", env,
        destination / "stdout.log", destination / "stderr.log")
    boundary_path = destination / "boundary.json"
    boundary = json.loads(boundary_path.read_text(encoding="utf-8")) \
        if boundary_path.is_file() else None
    collisions = read_jsonl(destination / "physical-collisions.jsonl")
    samples = branch_samples(
        destination / "vehicle-states.jsonl", float(args.event_time), end_time)
    manifest = {
        "record_type": "decision-oracle-branch", "event": event,
        "choice": choice, "command": command, "exit_code": code,
        "elapsed_seconds": elapsed, "boundary": boundary,
        "completed": code == 0 and boundary is not None,
        "source_unchanged": source_hashes(source) == initial_hashes,
        "restore_fingerprint_match": bool(
            boundary and (expected_fingerprint is None
                          or boundary["fingerprint"] == expected_fingerprint)),
        "safety": {"valid": not collisions,
                   "physical_collision_records": len(collisions)},
        "sample_vehicle_count": len(samples),
        "sample_count": sum(len(values) for values in samples.values()),
    }
    write_json(destination / "manifest.json", manifest)
    if (not manifest["completed"] or not manifest["source_unchanged"]
            or not manifest["restore_fingerprint_match"]):
        raise RuntimeError(f"{choice} branch did not complete validly")
    return manifest, samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--event-ordinal", type=int, required=True)
    parser.add_argument("--event-time", type=float, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output directory already exists")
    if args.event_ordinal < 1:
        parser.error("event ordinal must be positive")

    args.output.mkdir(parents=True)
    event = {"case": "eval3", "seed": args.seed,
             "ordinal": args.event_ordinal, "sim_time_s": args.event_time}
    event_dir = args.output / f"event-{args.event_ordinal:04d}"
    event_dir.mkdir()
    source, initial_hashes = prepare_source(event_dir, "eval3")
    checkpoint = run_capture(args, event, source, event_dir, initial_hashes)
    accept, accept_samples = run_branch(
        args, event, source, event_dir, initial_hashes, checkpoint, "accept")
    fingerprint = accept["boundary"]["fingerprint"]
    reject, reject_samples = run_branch(
        args, event, source, event_dir, initial_hashes, checkpoint, "reject",
        expected_fingerprint=fingerprint)

    cohort = set(accept_samples) | set(reject_samples)
    accept_metrics = decision_oracle.realised_metrics(accept_samples, cohort)
    reject_metrics = decision_oracle.realised_metrics(reject_samples, cohort)
    accept_metrics["safety"] = accept["safety"]
    reject_metrics["safety"] = reject["safety"]
    oracle = decision_oracle.oracle_choice(accept_metrics, reject_metrics)
    policy_choices = {
        "yamashita": accept["boundary"].get("yamashita_choice"),
        "proposal": accept["boundary"].get("proposal_choice"),
    }
    policy_scores = {
        name: decision_oracle.score_policy(choice, accept_metrics,
                                           reject_metrics, oracle)
        for name, choice in policy_choices.items()
    }
    manifest = {
        "schema": "decision-oracle-event-v1", "event": event,
        "checkpoint": str(checkpoint),
        "branches": {
            "accept": {**accept, "metrics": accept_metrics},
            "reject": {**reject, "metrics": reject_metrics},
        },
        "boundary_fingerprint": fingerprint,
        "policy_choices": policy_choices, "oracle": oracle,
        "policy_scores": policy_scores,
        "cohort_vehicle_ids": sorted(cohort),
    }
    write_json(event_dir / "manifest.json", manifest)
    experiment = {
        "schema": "decision-oracle-experiment-v1",
        "events": [event_dir.name], "event_count": 1,
        "summary": decision_oracle.summarize([manifest]),
        "git": git_metadata(),
        "source_unchanged": source_hashes(source) == initial_hashes,
        "exit_code": 0,
    }
    write_json(args.output / "manifest.json", experiment)
    print(json.dumps(experiment["summary"], indent=2))


if __name__ == "__main__":
    main()

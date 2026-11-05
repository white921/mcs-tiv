#!/usr/bin/env python3
"""Audit and aggregate the preregistered time-stratified oracle holdout."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path


CASES = ("eval3", "eval5", "eval7")
WINDOWS = ("0-100", "100-160", "160-220", "220-290")
WINDOW_BOUNDS = {
    "0-100": (0.0, 100.0, False),
    "100-160": (100.0, 160.0, False),
    "160-220": (160.0, 220.0, False),
    "220-290": (220.0, 290.0, True),
}
POLICIES = ("arrival_only", "proposal_lambda_2", "yamashita")
EXPECTED_PLAN_HASHES = {
    (13, 17, "0-100"): "3da2c236ad273ee73603504046f8051ad7b60cf9918e52f8b6d7cc24f2f3a01c",
    (13, 17, "100-160"): "c5d6599267f0a0fcc6b80e5dc1a080a652ac8fe49997eeac5a3530fb2b30aa96",
    (13, 17, "160-220"): "313a3b236f845133d3aefcdf2a3da844521b2e00ccf79feaa0cc4af6509ba59e",
    (13, 17, "220-290"): "297bc4d5dd8557a12001fac768f525f28b288d94edd7e91070e7e6196306edd3",
    (18, 22, "0-100"): "232444c4052bd421bda2077077e92da8488ab79acc8f000ff5ba6cd3800ca749",
    (18, 22, "100-160"): "1de633272a8dd794afd68f9f4edaaa87d96177081761aa99b168505cced9fbc5",
    (18, 22, "160-220"): "c5ecbd97871bdbe71e20f55df327b88275b83b534a8c8ca915496a18adf18034",
    (18, 22, "220-290"): "c0d1d07afda5e21ba28319bec36acdaa13705aadd467d4497c55b5ad00870ab6",
}
EXPECTED_SOURCE_COMMITS = {
    "f8412b944a4dcdaf42df8b556bebbc825572f6f8",
    "3862a8771044c7ed6807f9da1b2587926aba3ef3",
}
FATAL_LOG_PATTERN = re.compile(
    r"Traceback \(most recent call last\)|Segmentation fault|Unhandled exception|Fatal error",
    re.IGNORECASE,
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def identity(event: dict) -> tuple:
    return (
        event["case"], int(event["seed"]), event["origin_policy"],
        int(event["ordinal"]), float(event["sim_time_s"]),
        str(event["receiver_id"]), str(event["sender_id"]),
        str(event["desired_path_id"]),
    )


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty percentile input")
    index = min(
        len(ordered) - 1,
        max(0, math.ceil(probability * len(ordered)) - 1),
    )
    return ordered[index]


def macro_cell_mean(rows: list[dict], field: str) -> float | None:
    cells = []
    for case in CASES:
        for window in WINDOWS:
            values = [
                row[field] for row in rows
                if row["case"] == case and row["window"] == window
                and row.get(field) is not None
            ]
            if values:
                cells.append(statistics.fmean(values))
    return statistics.fmean(cells) if cells else None


def cluster_bootstrap(
    rows: list[dict], field: str, repetitions: int, seed: int,
) -> list[float]:
    """Resample origin-policy x seed clusters inside each case.

    Each sampled cluster contributes all four time bands. The draw is averaged
    over time bands inside a case and then over the three cases, matching the
    preregistered equal case/time-band estimand.
    """
    grouped: dict[str, dict[tuple[str, int], dict[str, list[float]]]] = (
        defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    )
    for row in rows:
        grouped[row["case"]][(row["origin_policy"], row["seed"])][
            row["window"]
        ].append(row[field])
    for case in CASES:
        if not grouped[case]:
            raise ValueError(f"no clusters for {case}")
        for window in WINDOWS:
            if not any(grouped[case][key][window] for key in grouped[case]):
                raise ValueError(f"no values for {case}:{window}")

    rng = random.Random(seed)
    draws = []
    for _ in range(repetitions):
        case_means = []
        for case in CASES:
            clusters = sorted(grouped[case])
            sampled = [rng.choice(clusters) for _ in clusters]
            window_means = []
            for window in WINDOWS:
                values = [
                    value for cluster in sampled
                    for value in grouped[case][cluster][window]
                ]
                if not values:
                    raise ValueError(
                        f"bootstrap draw has no values for {case}:{window}"
                    )
                window_means.append(statistics.fmean(values))
            case_means.append(statistics.fmean(window_means))
        draws.append(statistics.fmean(case_means))
    return sorted(draws)


def subset_summary(rows: list[dict], baseline: str, proposal: str) -> dict:
    common = [
        row for row in rows
        if row.get(f"{baseline}_regret_m") is not None
        and row.get(f"{proposal}_regret_m") is not None
    ]
    difference = f"{proposal}_minus_{baseline}_regret_m"
    for row in common:
        row[difference] = (
            row[f"{proposal}_regret_m"] - row[f"{baseline}_regret_m"]
        )
    return {
        "common_events": len(common),
        "baseline_macro_regret_m": macro_cell_mean(
            common, f"{baseline}_regret_m"
        ),
        "proposal_macro_regret_m": macro_cell_mean(
            common, f"{proposal}_regret_m"
        ),
        "proposal_minus_baseline_macro_regret_m": macro_cell_mean(
            common, difference
        ),
    }


def comparison(
    rows: list[dict], baseline: str, proposal: str,
    repetitions: int, seed: int,
) -> dict:
    common = [
        row for row in rows
        if row.get(f"{baseline}_regret_m") is not None
        and row.get(f"{proposal}_regret_m") is not None
    ]
    difference = f"{proposal}_minus_{baseline}_regret_m"
    for row in common:
        row[difference] = (
            row[f"{proposal}_regret_m"] - row[f"{baseline}_regret_m"]
        )
    draws = cluster_bootstrap(common, difference, repetitions, seed)
    output = subset_summary(common, baseline, proposal)
    output["cluster_bootstrap_95pct_m"] = [
        percentile(draws, 0.025), percentile(draws, 0.975)
    ]
    output["by_window"] = {
        window: subset_summary(
            [row for row in common if row["window"] == window],
            baseline, proposal,
        )
        for window in WINDOWS
    }
    output["by_case"] = {
        case: subset_summary(
            [row for row in common if row["case"] == case],
            baseline, proposal,
        )
        for case in CASES
    }
    output["by_origin"] = {
        origin: subset_summary(
            [row for row in common if row["origin_policy"] == origin],
            baseline, proposal,
        )
        for origin in ("yamashita", "proposal")
    }
    return output


def policy_summary(rows: list[dict], policy: str) -> dict:
    scored = [row for row in rows if row.get(f"{policy}_regret_m") is not None]
    regrets = [row[f"{policy}_regret_m"] for row in scored]
    return {
        "scored_events": len(scored),
        "coverage": len(scored) / len(rows),
        "correct": sum(row[f"{policy}_correct"] is True for row in scored),
        "accuracy": (
            sum(row[f"{policy}_correct"] is True for row in scored) / len(scored)
            if scored else None
        ),
        "macro_case_window_mean_regret_m": macro_cell_mean(
            scored, f"{policy}_regret_m"
        ),
        "event_mean_regret_m": statistics.fmean(regrets) if regrets else None,
        "median_regret_m": statistics.median(regrets) if regrets else None,
        "p95_regret_m": percentile(regrets, 0.95) if regrets else None,
    }


def require_file(path: Path, errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"missing file: {path}")


def audit_corpus(
    window: str, root: Path, *,
    expected_plan_hashes: dict | None = None,
    expected_source_commits: set[str] | None = None,
    policies: tuple[str, ...] = POLICIES,
) -> tuple[list[dict], dict, list[str]]:
    errors = []
    for name in ("manifest.json", "plan.json", "run-git-metadata.json", "runner.log"):
        require_file(root / name, errors)
    if errors:
        return [], {}, errors
    manifest = read_json(root / "manifest.json")
    plan_bytes = (root / "plan.json").read_bytes()
    plan = json.loads(plan_bytes)
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    seeds = sorted({int(event["seed"]) for event in plan.get("events", [])})
    key = (min(seeds, default=-1), max(seeds, default=-1), window)
    expected_hash = (expected_plan_hashes or EXPECTED_PLAN_HASHES).get(key)
    source_commits = expected_source_commits or EXPECTED_SOURCE_COMMITS
    requires_exact_checkpoints = "oracle_aligned_v2" in policies
    checks = {
        "schema": manifest.get("schema") == "decision-oracle-corpus-v1",
        "status": manifest.get("status") == "completed",
        "planned_event_count": manifest.get("planned_event_count") == 120,
        "completed_event_count": manifest.get("completed_event_count") == 120,
        "failed_event_count": manifest.get("failed_event_count") == 0,
        "source_unchanged": manifest.get("source_unchanged") is True,
        "git_clean": manifest.get("git", {}).get("dirty") is False,
        "source_commit": manifest.get("git", {}).get("commit") in source_commits,
        "workers": manifest.get("workers") == 10,
        "cohort_mode": manifest.get("cohort_mode") == "actors-followers",
        "lambda": float(manifest.get("deceleration_loss_lambda", -1)) == 2.0,
        "exact_checkpoint_events": (
            not requires_exact_checkpoints
            or manifest.get("exact_checkpoint_event_count") == 120),
        "no_legacy_capture_resume": (
            not requires_exact_checkpoints
            or manifest.get("capture_resume_event_count") == 0),
        "exact_checkpoint_batch": (
            not requires_exact_checkpoints
            or manifest.get("exact_checkpoint_batch", {}).get(
                "manifest", {}).get("status") == "completed"),
        "plan_hash_manifest": manifest.get("plan_sha256") == plan_hash,
        "plan_hash_preregistered": expected_hash == plan_hash,
        "plan_event_count": len(plan.get("events", [])) == 120,
        "seed_group": seeds == list(range(key[0], key[1] + 1)),
    }
    for name, passed in checks.items():
        if not passed:
            errors.append(f"{root}: failed corpus check {name}")

    lower, upper, include_upper = WINDOW_BOUNDS[window]
    plan_events = {identity(event) for event in plan.get("events", [])}
    event_paths = sorted(root.glob("events/*/*/manifest.json"))
    if len(event_paths) != 120:
        errors.append(f"{root}: expected 120 event manifests, got {len(event_paths)}")
    rows = []
    observed_events = set()
    collision_records = 0
    fatal_logs = []
    fingerprints_checked = 0
    for event_path in event_paths:
        event_manifest = read_json(event_path)
        event = event_manifest.get("event", {})
        try:
            event_id = identity(event)
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"{event_path}: invalid event identity: {error}")
            continue
        observed_events.add(event_id)
        sim_time = float(event["sim_time_s"])
        in_window = lower <= sim_time <= upper if include_upper else lower <= sim_time < upper
        if not in_window:
            errors.append(f"{event_path}: time {sim_time} outside {window}")
        if event_manifest.get("schema") != "decision-oracle-event-v2":
            errors.append(f"{event_path}: unexpected schema")
        if event_manifest.get("git", {}).get("dirty") is not False:
            errors.append(f"{event_path}: dirty event source")
        branches = event_manifest.get("branches", {})
        try:
            accept_fingerprint = branches["accept"]["boundary"]["fingerprint"]
            reject_fingerprint = branches["reject"]["boundary"]["fingerprint"]
            if accept_fingerprint != reject_fingerprint:
                errors.append(f"{event_path}: branch fingerprint mismatch")
            else:
                fingerprints_checked += 1
        except KeyError:
            errors.append(f"{event_path}: missing branch fingerprint")

        event_dir = event_path.parent
        outer_dir = event_dir.parent
        outer_manifest_path = outer_dir / "manifest.json"
        require_file(outer_manifest_path, errors)
        if outer_manifest_path.is_file():
            outer = read_json(outer_manifest_path)
            if outer.get("exit_code") != 0 or outer.get("source_unchanged") is not True:
                errors.append(f"{outer_manifest_path}: invalid event run")
        for choice in ("accept", "reject"):
            branch_dir = event_dir / choice
            for name in (
                "boundary.json", "evaluation-metrics.json", "manifest.json",
                "negotiations.jsonl", "physical-collisions.jsonl",
                "stderr.log", "stdout.log", "vehicle-states.jsonl",
            ):
                require_file(branch_dir / name, errors)
            branch_manifest_path = branch_dir / "manifest.json"
            if branch_manifest_path.is_file():
                branch_manifest = read_json(branch_manifest_path)
                if (branch_manifest.get("exit_code") != 0
                        or branch_manifest.get("source_unchanged") is not True):
                    errors.append(f"{branch_manifest_path}: invalid branch")
            collisions = branch_dir / "physical-collisions.jsonl"
            if collisions.is_file():
                collision_records += sum(
                    1 for line in collisions.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines() if line.strip()
                )
        capture_dir = event_dir / "capture"
        for name in ("manifest.json", "negotiations.jsonl", "stderr.log", "stdout.log"):
            require_file(capture_dir / name, errors)
        capture_manifest_path = capture_dir / "manifest.json"
        if capture_manifest_path.is_file():
            capture_manifest = read_json(capture_manifest_path)
            if (capture_manifest.get("exit_code") != 0
                    or capture_manifest.get("source_unchanged") is not True):
                errors.append(f"{capture_manifest_path}: invalid capture")
        checkpoint_dirs = list((capture_dir / "checkpoints").glob("t*"))
        if len(checkpoint_dirs) != 1:
            errors.append(f"{capture_dir}: expected one checkpoint, got {len(checkpoint_dirs)}")
        else:
            for name in ("checkpoint.json", "mcs-state.pkl", "sumo-state.xml.gz"):
                require_file(checkpoint_dirs[0] / name, errors)
        for log_path in event_dir.rglob("stderr.log"):
            text = log_path.read_text(encoding="utf-8", errors="replace")
            if FATAL_LOG_PATTERN.search(text):
                fatal_logs.append(str(log_path))

        row = {
            "case": event["case"],
            "window": window,
            "origin_policy": event["origin_policy"],
            "seed": int(event["seed"]),
            "ordinal": int(event["ordinal"]),
            "sim_time_s": sim_time,
            "receiver_id": str(event["receiver_id"]),
            "sender_id": str(event["sender_id"]),
            "desired_path_id": str(event["desired_path_id"]),
            "oracle_choice": event_manifest.get("oracle", {}).get("choice"),
            "accept_minus_reject_distance_m": event_manifest.get(
                "oracle", {}
            ).get("accept_minus_reject_distance_m"),
            "corpus": root.name,
        }
        for policy in policies:
            score = event_manifest.get("policy_scores", {}).get(policy, {})
            row[f"{policy}_choice"] = event_manifest.get(
                "policy_choices", {}
            ).get(policy)
            row[f"{policy}_scored"] = score.get("scored") is True
            row[f"{policy}_correct"] = (
                score.get("correct") if score.get("scored") is True else None
            )
            row[f"{policy}_regret_m"] = (
                float(score["regret_m"])
                if score.get("scored") is True else None
            )
        rows.append(row)

    if observed_events != plan_events:
        missing = len(plan_events - observed_events)
        extra = len(observed_events - plan_events)
        errors.append(f"{root}: plan/result mismatch missing={missing} extra={extra}")
    if collision_records:
        errors.append(f"{root}: physical collision records={collision_records}")
    runner_logs = list((root / "runner-logs").glob("*.log"))
    if len(runner_logs) != 240:
        errors.append(f"{root}: expected 240 runner logs, got {len(runner_logs)}")
    for log_path in runner_logs + [root / "runner.log"]:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        if FATAL_LOG_PATTERN.search(text):
            fatal_logs.append(str(log_path))
    if fatal_logs:
        errors.append(f"{root}: fatal log signatures={len(fatal_logs)}")

    audit = {
        "corpus": root.name,
        "window": window,
        "seed_min": key[0],
        "seed_max": key[1],
        "source_commit": manifest.get("git", {}).get("commit"),
        "plan_sha256": plan_hash,
        "event_count": len(rows),
        "fingerprints_checked": fingerprints_checked,
        "branch_count": 2 * len(rows),
        "physical_collision_records": collision_records,
        "runner_log_count": len(runner_logs),
        "capture_resume_event_count": manifest.get("capture_resume_event_count", 0),
        "exact_checkpoint_event_count": manifest.get(
            "exact_checkpoint_event_count", 0),
        "errors": errors,
    }
    return rows, audit, errors


def parse_corpus(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("use WINDOW=PATH")
    window, path = value.split("=", 1)
    if window not in WINDOW_BOUNDS:
        raise argparse.ArgumentTypeError(f"unsupported window: {window}")
    return window, Path(path).resolve()


def load_expected_plan_hashes(path: Path) -> dict[tuple[int, int, str], str]:
    source = read_json(path)
    output = {}
    for name, value in source.items():
        try:
            seed_range, window = name.split(":", 1)
            seed_min, seed_max = map(int, seed_range.split("-", 1))
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"invalid expected plan hash key {name!r}; "
                "use SEED_MIN-SEED_MAX:WINDOW") from error
        if window not in WINDOWS or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"invalid expected plan hash entry: {name}={value}")
        output[(seed_min, seed_max, window)] = value
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", action="append", type=parse_corpus, required=True,
        help="repeat eight times as WINDOW=PATH",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-repetitions", type=int, default=100_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20261103)
    parser.add_argument(
        "--proposal-policy", default="proposal_lambda_2",
        help="policy field compared with arrival_only and yamashita")
    parser.add_argument(
        "--expected-plan-hashes", type=Path,
        help="JSON map keyed as SEED_MIN-SEED_MAX:WINDOW")
    parser.add_argument(
        "--expected-source-commit", action="append",
        help="allowed clean source commit; repeat when needed")
    args = parser.parse_args()
    if len(args.corpus) != 8:
        parser.error("exactly eight corpus roots are required")
    if args.output.exists():
        parser.error("output directory already exists")
    args.output.mkdir(parents=True)
    if not re.fullmatch(r"[a-z0-9_]+", args.proposal_policy):
        parser.error("--proposal-policy must be a policy field name")
    try:
        expected_hashes = (
            load_expected_plan_hashes(args.expected_plan_hashes)
            if args.expected_plan_hashes else EXPECTED_PLAN_HASHES)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    expected_commits = (
        set(args.expected_source_commit)
        if args.expected_source_commit else EXPECTED_SOURCE_COMMITS)
    policies = tuple(dict.fromkeys(
        ("arrival_only", args.proposal_policy, "yamashita")))

    rows = []
    corpus_audits = []
    errors = []
    for window, root in args.corpus:
        corpus_rows, audit, corpus_errors = audit_corpus(
            window, root,
            expected_plan_hashes=expected_hashes,
            expected_source_commits=expected_commits,
            policies=policies)
        rows.extend(corpus_rows)
        corpus_audits.append(audit)
        errors.extend(corpus_errors)
    if len(rows) != 960:
        errors.append(f"expected 960 events, got {len(rows)}")
    expected_windows = {window: 2 for window in WINDOWS}
    actual_windows = {
        window: sum(item[0] == window for item in args.corpus)
        for window in WINDOWS
    }
    if actual_windows != expected_windows:
        errors.append(f"unexpected corpus windows: {actual_windows}")

    audit_output = {
        "schema": "time-stratified-decision-oracle-audit-v1",
        "status": "passed" if not errors else "failed",
        "event_count": len(rows),
        "branch_count": 2 * len(rows),
        "physical_collision_records": sum(
            item.get("physical_collision_records", 0) for item in corpus_audits
        ),
        "corpora": corpus_audits,
        "errors": errors,
    }
    (args.output / "audit.json").write_text(
        json.dumps(audit_output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if errors:
        raise SystemExit(f"audit failed with {len(errors)} errors; see audit.json")

    primary = comparison(
        rows, "arrival_only", args.proposal_policy,
        args.bootstrap_repetitions, args.bootstrap_seed,
    )
    secondary = comparison(
        rows, "yamashita", args.proposal_policy,
        args.bootstrap_repetitions, args.bootstrap_seed + 10_000,
    )
    summary = {
        "schema": "time-stratified-decision-oracle-analysis-v1",
        "event_count": len(rows),
        "branch_count": 2 * len(rows),
        "cases": list(CASES),
        "windows_s": list(WINDOWS),
        "bootstrap": {
            "repetitions": args.bootstrap_repetitions,
            "seed": args.bootstrap_seed,
            "cluster": "origin_policy x seed within case",
            "aggregation": "equal case x time-window macro mean",
        },
        "proposal_policy": args.proposal_policy,
        "policies": {policy: policy_summary(rows, policy) for policy in policies},
        "primary_candidate_vs_arrival_only": primary,
        "secondary_candidate_vs_yamashita": secondary,
        # Backward-compatible aliases retained for the completed 2026-11-03
        # analysis and any existing readers of its schema.
        "primary_proposal_vs_arrival_only": primary,
        "secondary_proposal_vs_yamashita": secondary,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    fieldnames = sorted({key for row in rows for key in row})
    with (args.output / "events.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    run_manifest = {
        "schema": "time-stratified-decision-oracle-analysis-run-v1",
        "status": "completed",
        "analysis_only": True,
        "new_simulation": False,
        "event_count": len(rows),
        "corpus_roots": [str(root) for _, root in args.corpus],
        "output_files": ["audit.json", "summary.json", "events.csv"],
    }
    (args.output / "experiment-manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "audit": audit_output["status"],
        "events": len(rows),
        "primary": primary,
        "secondary": secondary,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

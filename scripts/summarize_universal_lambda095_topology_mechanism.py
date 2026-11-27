#!/usr/bin/env python3
"""Summarize post-hoc topology diagnostics for the lambda=0.95 holdout."""

from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "scripts" / "run_universal_lambda095_holdout.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEDULER = load_module("lambda095_holdout_scheduler", SCHEDULER_PATH)

COUNT_KEYS = (
    "active_attempts",
    "active_evaluations",
    "active_unsupported",
    "decision_agreement",
    "decision_disagreement",
    "proposal_accept",
    "proposal_reject",
    "tiv_would_accept",
    "tiv_would_reject",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def finite_float(value, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError(f"{name} is not finite: {value!r}")
    return result


def mean(values: list[float]) -> float:
    if not values:
        raise RuntimeError("cannot summarize an empty record sample")
    return statistics.mean(values)


def summarize_audits(audits: list[dict]) -> dict:
    if not audits:
        raise RuntimeError("no deceleration audits supplied")
    lambdas = {finite_float(audit.get("convex_lambda"), "convex_lambda") for audit in audits}
    if len(lambdas) != 1:
        raise RuntimeError(f"audit lambda mismatch: {sorted(lambdas)}")
    lambda_value = lambdas.pop()
    if not math.isclose(lambda_value, SCHEDULER.LAMBDA):
        raise RuntimeError(
            f"unexpected lambda {lambda_value}; expected {SCHEDULER.LAMBDA}"
        )

    counts = {
        key: sum(int(audit.get("counts", {}).get(key, 0)) for audit in audits)
        for key in COUNT_KEYS
    }
    records = [record for audit in audits for record in audit.get("records", [])]
    evaluated = [record for record in records if record.get("status") == "evaluated"]
    unsupported = [record for record in records if record.get("status") == "unsupported"]
    if not evaluated:
        raise RuntimeError("no retained evaluated records")

    follower_counts = [
        finite_float(record.get("follower_count"), "follower_count")
        for record in evaluated
    ]
    z_time = [finite_float(record.get("z_time"), "z_time") for record in evaluated]
    z_follow = [
        finite_float(record.get("z_follow"), "z_follow") for record in evaluated
    ]
    weighted_time = [abs((1.0 - lambda_value) * value) for value in z_time]
    weighted_follow = [abs(lambda_value * value) for value in z_follow]
    mean_weighted_time = mean(weighted_time)
    mean_weighted_follow = mean(weighted_follow)
    attempts = counts["active_attempts"]
    evaluations = counts["active_evaluations"]

    return {
        "run_count": len(audits),
        "lambda": lambda_value,
        "exact_counts": counts,
        "exact_rates": {
            "evaluation_rate": evaluations / attempts if attempts else None,
            "unsupported_rate": counts["active_unsupported"] / attempts
            if attempts
            else None,
            "decision_disagreement_rate": counts["decision_disagreement"]
            / evaluations
            if evaluations
            else None,
            "proposal_accept_rate": counts["proposal_accept"] / evaluations
            if evaluations
            else None,
        },
        "retained_record_sample": {
            "record_count": len(records),
            "evaluated_count": len(evaluated),
            "unsupported_count": len(unsupported),
            "is_truncated": len(records) < attempts,
            "unsupported_reasons": dict(
                sorted(
                    Counter(
                        str(record.get("reason", "unknown"))
                        for record in unsupported
                    ).items()
                )
            ),
            "follower_count_mean": mean(follower_counts),
            "follower_count_median": statistics.median(follower_counts),
            "follower_zero_rate": sum(value == 0 for value in follower_counts)
            / len(follower_counts),
            "mean_abs_z_time": mean([abs(value) for value in z_time]),
            "mean_abs_z_follow": mean([abs(value) for value in z_follow]),
            "mean_abs_weighted_time": mean_weighted_time,
            "mean_abs_weighted_follow": mean_weighted_follow,
            "weighted_follow_to_time_ratio": mean_weighted_follow
            / mean_weighted_time
            if mean_weighted_time
            else None,
            "nonzero_follow_rate": sum(abs(value) > 1e-12 for value in z_follow)
            / len(z_follow),
        },
    }


def validate_proposal_run(run: Path, seed: int, source_commit: str) -> dict:
    manifest_path = run / "manifest.json"
    audit_path = run / "deceleration-audit.json"
    if not manifest_path.is_file() or not audit_path.is_file():
        raise RuntimeError(f"missing manifest or deceleration audit: {run}")
    manifest = read_json(manifest_path)
    checks = {
        "exit_code": manifest.get("exit_code") == 0,
        "source_unchanged": manifest.get("source_unchanged") is True,
        "source_commit": manifest.get("git", {}).get("commit") == source_commit,
        "git_clean": manifest.get("git", {}).get("dirty") is False,
        "seed": manifest.get("seed") == seed,
        "duration": manifest.get("input_duration") == 600.0,
        "method": manifest.get("decision_method")
        == "normalized-deceleration-propagation",
        "lambda": math.isclose(
            finite_float(
                manifest.get("deceleration_prediction", {}).get("convex_lambda"),
                "manifest lambda",
            ),
            SCHEDULER.LAMBDA,
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"{run}: failed checks {failed}")
    return read_json(audit_path)


def compact_performance(comparison: dict) -> dict:
    return {
        "yamashita_all_speed_mean_mps": comparison["yamashita"][
            "all_speed_mean_mps"
        ],
        "proposal_all_speed_mean_mps": comparison["proposal"][
            "all_speed_mean_mps"
        ],
        "speed_difference_mean_mps": comparison["speed_difference_mean_mps"],
        "speed_improvement_from_means_percent": comparison[
            "speed_improvement_from_means_percent"
        ],
        "proposal_faster_seed_count": comparison["proposal_faster_seed_count"],
        "paired_bootstrap_95_percent_mps": comparison[
            "paired_bootstrap_95_percent_mps"
        ],
    }


def build_report(root: Path, date_tag: str, source_commit: str) -> dict:
    first_output = root / "results" / "runs" / SCHEDULER.output_name(
        SCHEDULER.CONDITION_ORDER[0], "proposal", date_tag
    )
    summary_path = first_output / "universal-holdout-summary.json"
    if not summary_path.is_file():
        raise RuntimeError(f"final holdout summary is missing: {summary_path}")
    summary = read_json(summary_path)
    if (
        summary.get("run_count") != 60
        or summary.get("source_commit") != source_commit
        or summary.get("all_pre_compression_checks_passed") is not True
    ):
        raise RuntimeError("final holdout summary has not passed the required audit")
    comparisons = {
        comparison["condition"]: comparison
        for comparison in summary.get("comparisons", [])
    }

    conditions = {}
    for condition in SCHEDULER.CONDITION_ORDER:
        spec = SCHEDULER.CONDITION_SPECS[condition]
        output = root / "results" / "runs" / SCHEDULER.output_name(
            condition, "proposal", date_tag
        )
        audits = [
            validate_proposal_run(
                output / spec["case"] / f"seed-{seed}", seed, source_commit
            )
            for seed in SCHEDULER.SEEDS
        ]
        if condition not in comparisons:
            raise RuntimeError(f"performance comparison missing for {condition}")
        conditions[condition] = {
            "case": spec["case"],
            "flows_vph": list(spec["flows"]),
            "performance": compact_performance(comparisons[condition]),
            "mechanism": summarize_audits(audits),
        }

    return {
        "schema_version": 1,
        "analysis": "universal-lambda095-post-hoc-topology-mechanism",
        "classification": "post-hoc exploratory",
        "source_commit": source_commit,
        "date_tag": date_tag,
        "conditions": conditions,
        "caveats": [
            "The performance comparison is the preregistered formal holdout result.",
            "The mechanism analysis was specified after development results were viewed.",
            "Exact rates use full audit counters, but retained records are a capped, time-ordered sample rather than a random sample.",
            "Associations between topology diagnostics and performance do not by themselves establish causality.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--date-tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    report = build_report(root, args.date_tag, args.source_commit)
    output = args.output or (
        root
        / "results"
        / "runs"
        / f"universal-lambda095-topology-mechanism-{args.date_tag}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(output),
                "condition_count": len(report["conditions"]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

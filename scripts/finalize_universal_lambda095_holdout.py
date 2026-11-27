#!/usr/bin/env python3
"""Audit and summarize the completed universal lambda=0.95 holdout."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "scripts" / "run_universal_lambda095_holdout.py"
BASE_FINALIZER_PATH = ROOT / "scripts" / "finalize_eval35_lambda0525_comparison.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEDULER = load_module("lambda095_holdout_scheduler", SCHEDULER_PATH)
BASE = load_module("lambda095_holdout_base_finalizer", BASE_FINALIZER_PATH)
BASE.LAMBDA = SCHEDULER.LAMBDA
BASE.SEEDS = SCHEDULER.SEEDS


def context_from_output(root: Path, condition: str, method: str, date_tag: str):
    output = root / "results" / "runs" / SCHEDULER.output_name(
        condition, method, date_tag
    )
    experiment = json.loads((output / "experiment-manifest.json").read_text())
    if experiment.get("status") != "completed":
        raise RuntimeError(f"{output}: experiment is not completed")
    if experiment.get("completed_simulations") != len(SCHEDULER.SEEDS):
        raise RuntimeError(f"{output}: completed count mismatch")
    spec = SCHEDULER.CONDITION_SPECS[condition]
    expected_lambda = SCHEDULER.LAMBDA if method == "proposal" else None
    if (
        experiment.get("condition") != condition
        or experiment.get("case") != spec["case"]
        or experiment.get("flows_vph") != list(spec["flows"])
        or experiment.get("deceleration_convex_lambda") != expected_lambda
    ):
        raise RuntimeError(f"{output}: experiment manifest does not match plan")
    return {
        "tag": f"{condition}-{method}",
        "root": root,
        "output": output,
        "spec": {
            "eval": spec["case"],
            "condition": condition,
            "case": spec["case"],
            "flows": tuple(spec["flows"]),
            "method": method,
        },
    }


def paired_comparison(condition: str, rows):
    yamashita = {
        row["seed"]: row
        for row in rows
        if row["condition"] == condition and row["method"] == "yamashita"
    }
    proposal = {
        row["seed"]: row
        for row in rows
        if row["condition"] == condition and row["method"] == "proposal"
    }
    expected = set(SCHEDULER.SEEDS)
    if set(yamashita) != expected or set(proposal) != expected:
        raise RuntimeError(f"{condition}: incomplete paired seeds")
    pairs = []
    for seed in SCHEDULER.SEEDS:
        if (
            yamashita[seed]["fixed_input_sha256"]
            != proposal[seed]["fixed_input_sha256"]
        ):
            raise RuntimeError(f"{condition}/seed-{seed}: fixed input mismatch")
        difference = (
            proposal[seed]["all_speed_mps"]
            - yamashita[seed]["all_speed_mps"]
        )
        pairs.append(
            {
                "seed": seed,
                "yamashita_speed_mps": yamashita[seed]["all_speed_mps"],
                "proposal_speed_mps": proposal[seed]["all_speed_mps"],
                "difference_mps": difference,
                "improvement_percent": (
                    difference / yamashita[seed]["all_speed_mps"] * 100
                ),
            }
        )
    differences = [pair["difference_mps"] for pair in pairs]
    yam_rows = [yamashita[seed] for seed in SCHEDULER.SEEDS]
    proposal_rows = [proposal[seed] for seed in SCHEDULER.SEEDS]
    yam_mean = statistics.mean(row["all_speed_mps"] for row in yam_rows)
    proposal_mean = statistics.mean(row["all_speed_mps"] for row in proposal_rows)
    return {
        "condition": condition,
        "yamashita": BASE.aggregate(yam_rows),
        "proposal": BASE.aggregate(proposal_rows),
        "paired": pairs,
        "speed_difference_mean_mps": statistics.mean(differences),
        "speed_improvement_from_means_percent": (proposal_mean / yam_mean - 1) * 100,
        "proposal_faster_seed_count": sum(value > 0 for value in differences),
        "paired_bootstrap_95_percent_mps": BASE.bootstrap_interval(
            differences, seed=f"universal-lambda095:{condition}"
        ),
    }


def build_summary(rows, source_commit: str):
    comparisons = [
        paired_comparison(condition, rows)
        for condition in SCHEDULER.CONDITION_ORDER
    ]
    relative = [
        comparison["speed_improvement_from_means_percent"]
        for comparison in comparisons
    ]
    return {
        "schema_version": 1,
        "experiment_id": "universal-lambda095-final-holdout",
        "classification": "formal",
        "source_commit": source_commit,
        "lambda": SCHEDULER.LAMBDA,
        "seeds": list(SCHEDULER.SEEDS),
        "run_count": len(rows),
        "all_pre_compression_checks_passed": True,
        "per_run": rows,
        "comparisons": comparisons,
        "topology_balanced_relative_improvement_percent": statistics.mean(relative),
        "worst_condition_relative_improvement_percent": min(relative),
        "proposal_faster_in_all_conditions": all(value > 0 for value in relative),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--date-tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 2:
        parser.error("--workers must be 1 or 2")
    root = args.root.resolve()

    contexts = [
        context_from_output(root, condition, method, args.date_tag)
        for condition in SCHEDULER.CONDITION_ORDER
        for method in SCHEDULER.METHOD_ORDER
    ]
    rows = [
        BASE.analyze_run(context, seed, args.source_commit)
        for context in contexts
        for seed in SCHEDULER.SEEDS
    ]
    errors = [
        f"{row['context']}/seed-{row['seed']}: {row['errors']}"
        for row in rows
        if row["errors"]
    ]
    if errors:
        raise RuntimeError("pre-compression audit failed:\n" + "\n".join(errors))
    summary = build_summary(rows, args.source_commit)

    sys.path.insert(0, str(ROOT / "scripts"))
    from compress_diagnostic_artifacts import process as compress  # noqa: E402

    for context in contexts:
        BASE.write_json(
            context["output"] / "universal-holdout-summary.json", summary
        )
        BASE.write_json(
            context["output"] / "post-run-audit.json",
            {
                "schema_version": 1,
                "ok": True,
                "phase": "pre-compression",
                "source_commit": args.source_commit,
                "run_count": len(SCHEDULER.SEEDS),
                "errors": [],
            },
        )

    for context in contexts:
        compress(context["output"], args.workers)
        removed = BASE.remove_source_snapshots(context["output"])
        compression = json.loads(
            (context["output"] / "compression-audit.json").read_text()
        )
        split = json.loads(
            (context["output"] / "storage-split-audit.json").read_text()
        )
        ok = (
            compression.get("all_verified") is True
            and split.get("all_verified") is True
        )
        if not ok:
            raise RuntimeError(f"{context['tag']}: compression verification failed")
        BASE.write_json(
            context["output"] / "post-run-audit.json",
            {
                "schema_version": 1,
                "ok": True,
                "phase": "complete",
                "source_commit": args.source_commit,
                "run_count": len(SCHEDULER.SEEDS),
                "compression_verified": True,
                "storage_split_verified": True,
                "compressed_item_count": compression.get("item_count"),
                "removed_reconstructable_source_snapshots": removed,
                "external_storage": "pending",
                "errors": [],
            },
        )
    print(json.dumps(summary, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

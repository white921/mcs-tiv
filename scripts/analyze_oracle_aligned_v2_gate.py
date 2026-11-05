#!/usr/bin/env python3
"""Analyze confidence gates for the oracle-aligned v2 distance prediction.

This is explicitly a development analysis: it selects and evaluates gates on
the same saved oracle outcomes.  Its output must not be described as holdout
confirmation.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_time_stratified_decision_oracle import (  # noqa: E402
    CASES,
    WINDOWS,
    cluster_bootstrap,
    macro_cell_mean,
    percentile,
)


THRESHOLDS_M = (0, 1, 2, 5, 10, 20, 30, 40, 50, 75, 100, 150, 200)
MODES = ("symmetric", "accept_to_reject", "reject_to_accept")
BOOTSTRAP_REPETITIONS = 100_000
BOOTSTRAP_SEED = 20261105


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", newline="") as stream:
        for source in csv.DictReader(stream):
            predicted = source["predicted_accept_minus_reject_m"]
            actual = source["actual_accept_minus_reject_m"]
            baseline = source["arrival_only_choice"]
            oracle = source["oracle_choice"]
            if not predicted or not actual or baseline not in ("accept", "reject"):
                continue
            rows.append({
                "case": source["case"],
                "window": source["window"],
                "origin_policy": source["origin_policy"],
                "seed": int(source["seed"]),
                "ordinal": int(source["ordinal"]),
                "predicted_m": float(predicted),
                "actual_m": float(actual),
                "baseline_choice": baseline,
                "oracle_choice": oracle,
            })
    return rows


def gated_choice(row: dict, threshold_m: float, mode: str) -> str:
    baseline = row["baseline_choice"]
    predicted = row["predicted_m"]
    if mode in ("symmetric", "accept_to_reject"):
        if baseline == "accept" and predicted < -threshold_m:
            return "reject"
    if mode in ("symmetric", "reject_to_accept"):
        if baseline == "reject" and predicted > threshold_m:
            return "accept"
    return baseline


def regret(row: dict, choice: str) -> float:
    return 0.0 if choice == row["oracle_choice"] else abs(row["actual_m"])


def score(rows: list[dict], threshold_m: float, mode: str) -> dict:
    evaluated = []
    changes = 0
    correct = 0
    for source in rows:
        row = dict(source)
        choice = gated_choice(row, threshold_m, mode)
        changes += choice != row["baseline_choice"]
        correct += choice == row["oracle_choice"]
        row["baseline_regret_m"] = regret(row, row["baseline_choice"])
        row["gated_regret_m"] = regret(row, choice)
        row["gated_minus_baseline_regret_m"] = (
            row["gated_regret_m"] - row["baseline_regret_m"])
        evaluated.append(row)
    return {
        "events": len(evaluated),
        "changed_decisions": changes,
        "accuracy": correct / len(evaluated),
        "baseline_macro_regret_m": macro_cell_mean(
            evaluated, "baseline_regret_m"),
        "gated_macro_regret_m": macro_cell_mean(evaluated, "gated_regret_m"),
        "gated_minus_baseline_macro_regret_m": macro_cell_mean(
            evaluated, "gated_minus_baseline_regret_m"),
    }


def fixed_gate_analysis(rows: list[dict], threshold_m: float) -> dict:
    output = score(rows, threshold_m, "accept_to_reject")
    evaluated = []
    for source in rows:
        row = dict(source)
        choice = gated_choice(row, threshold_m, "accept_to_reject")
        row["baseline_regret_m"] = regret(row, row["baseline_choice"])
        row["gated_regret_m"] = regret(row, choice)
        row["difference_m"] = row["gated_regret_m"] - row["baseline_regret_m"]
        evaluated.append(row)
    draws = cluster_bootstrap(
        evaluated, "difference_m", BOOTSTRAP_REPETITIONS, BOOTSTRAP_SEED)
    output["cluster_bootstrap_95pct_m"] = [
        percentile(draws, 0.025), percentile(draws, 0.975)]
    output["by_case"] = {
        case: score([row for row in rows if row["case"] == case],
                    threshold_m, "accept_to_reject")
        for case in CASES
    }
    output["by_window"] = {
        window: score([row for row in rows if row["window"] == window],
                      threshold_m, "accept_to_reject")
        for window in WINDOWS
    }
    return output


def leave_one_cluster_out(rows: list[dict]) -> dict:
    clusters = sorted({
        (row["case"], row["origin_policy"], row["seed"]) for row in rows
    })
    selected = []
    held_out = []
    for cluster in clusters:
        training = [row for row in rows if (
            row["case"], row["origin_policy"], row["seed"]) != cluster]
        candidates = [
            (score(training, threshold, "accept_to_reject")[
                "gated_macro_regret_m"], threshold)
            for threshold in THRESHOLDS_M
        ]
        threshold = min(candidates)[1]
        selected.append(threshold)
        for row in rows:
            if (row["case"], row["origin_policy"], row["seed"]) == cluster:
                item = dict(row)
                choice = gated_choice(item, threshold, "accept_to_reject")
                item["baseline_regret_m"] = regret(
                    item, item["baseline_choice"])
                item["crossfit_regret_m"] = regret(item, choice)
                item["difference_m"] = (
                    item["crossfit_regret_m"] - item["baseline_regret_m"])
                held_out.append(item)
    return {
        "clusters": len(clusters),
        "selected_threshold_counts": {
            str(key): value for key, value in sorted(Counter(selected).items())
        },
        "baseline_macro_regret_m": macro_cell_mean(
            held_out, "baseline_regret_m"),
        "crossfit_macro_regret_m": macro_cell_mean(
            held_out, "crossfit_regret_m"),
        "crossfit_minus_baseline_macro_regret_m": macro_cell_mean(
            held_out, "difference_m"),
    }


def analyze(rows: list[dict]) -> dict:
    return {
        "schema": "oracle-aligned-v2-gate-development-analysis-v1",
        "development_only": True,
        "reason": "gate selection and scoring use the same 960-event oracle corpus",
        "scored_events": len(rows),
        "threshold_candidates_m": list(THRESHOLDS_M),
        "threshold_sweep": {
            mode: {str(threshold): score(rows, threshold, mode)
                   for threshold in THRESHOLDS_M}
            for mode in MODES
        },
        "leave_one_case_origin_seed_cluster_out": leave_one_cluster_out(rows),
        "fixed_accept_to_reject_10m": fixed_gate_analysis(rows, 10),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows(args.events_csv)
    if not rows:
        parser.error("no scored v2 rows found")
    args.output.write_text(
        json.dumps(analyze(rows), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()

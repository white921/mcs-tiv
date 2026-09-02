#!/usr/bin/env python3

import argparse
import json

from evaluate_run_summary import evaluate_summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare cooperative and baseline run summaries"
    )
    parser.add_argument("cooperative_summary_json", help="Path to cooperative run summary JSON")
    parser.add_argument("baseline_summary_json", help="Path to baseline run summary JSON")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of plain text",
    )
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def compare_summaries(cooperative_summary, baseline_summary):
    cooperative_eval = evaluate_summary(cooperative_summary)
    baseline_eval = evaluate_summary(baseline_summary)

    coop_metrics = cooperative_summary.get("metrics", {})
    base_metrics = baseline_summary.get("metrics", {})

    comparison = {
        "paper_alignment_score_improvement": round(
            cooperative_eval["paper_alignment_score"]
            - baseline_eval["paper_alignment_score"],
            4,
        ),
        "mv2_speed_variance_improvement": round(
            base_metrics.get("mv2_speed_variance_deactivate_to_merge", 0.0)
            - coop_metrics.get("mv2_speed_variance_deactivate_to_merge", 0.0),
            4,
        ),
        "rv_speed_variance_improvement": round(
            base_metrics.get("rv_speed_variance_observable_to_merge", 0.0)
            - coop_metrics.get("rv_speed_variance_observable_to_merge", 0.0),
            4,
        ),
        "rv_advisory_mismatch_change": round(
            base_metrics.get("rv_mean_abs_advisory_mismatch", 0.0)
            - coop_metrics.get("rv_mean_abs_advisory_mismatch", 0.0),
            4,
        ),
    }
    return {
        "cooperative_evaluation": cooperative_eval,
        "baseline_evaluation": baseline_eval,
        "comparison": comparison,
    }


def main():
    args = parse_args()
    cooperative_summary = load_json(args.cooperative_summary_json)
    baseline_summary = load_json(args.baseline_summary_json)
    result = compare_summaries(cooperative_summary, baseline_summary)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    cooperative_eval = result["cooperative_evaluation"]
    baseline_eval = result["baseline_evaluation"]
    comparison = result["comparison"]
    print(f"cooperative_score={cooperative_eval['paper_alignment_score']:.4f}")
    print(f"baseline_score={baseline_eval['paper_alignment_score']:.4f}")
    print(f"comparison={comparison}")
    print(f"cooperative_deltas={cooperative_eval['deltas']}")
    print(f"baseline_deltas={baseline_eval['deltas']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import json


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate a cooperative ramp merge run summary against paper targets"
    )
    parser.add_argument("summary_json", help="Path to run summary JSON")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of plain text",
    )
    return parser.parse_args()


def bounded_score(error_value, tolerance):
    if error_value is None:
        return 0.0
    normalized = min(abs(error_value) / tolerance, 1.0)
    return 1.0 - normalized


def evaluate_summary(summary):
    deltas = summary.get("paper_timeline_deltas", {})
    metrics = summary.get("metrics", {})

    leader_switch_error = deltas.get("leader_switch_error_vs_8s")
    flag2_error = deltas.get("flag2_activation_error_vs_8s")
    speed_sync_error = deltas.get("speed_sync_start_error_vs_15s")
    mv2_variance = metrics.get("mv2_speed_variance_deactivate_to_merge", 0.0)
    rv_mismatch = metrics.get("rv_mean_abs_advisory_mismatch", 0.0)

    subscores = {
        "leader_switch": bounded_score(leader_switch_error, 4.0),
        "flag2_activation": bounded_score(flag2_error, 4.0),
        "speed_sync_start": bounded_score(speed_sync_error, 5.0),
        "mv2_speed_variance": 1.0 / (1.0 + max(mv2_variance, 0.0)),
        "rv_advisory_mismatch": 1.0 / (1.0 + max(rv_mismatch, 0.0)),
    }

    overall_score = sum(subscores.values()) / len(subscores)
    return {
        "paper_alignment_score": round(overall_score, 4),
        "subscores": subscores,
        "deltas": deltas,
        "metrics": metrics,
    }


def main():
    args = parse_args()
    with open(args.summary_json, "r", encoding="utf-8") as summary_file:
        summary = json.load(summary_file)

    result = evaluate_summary(summary)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    print(f"paper_alignment_score={result['paper_alignment_score']:.4f}")
    print(f"subscores={result['subscores']}")
    print(f"deltas={result['deltas']}")
    print(f"metrics={result['metrics']}")


if __name__ == "__main__":
    main()

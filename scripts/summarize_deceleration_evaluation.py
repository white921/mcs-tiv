#!/usr/bin/env python3
"""Create a machine-readable and Markdown comparison from two Eval.3 runs."""
import argparse
import json
import math
import statistics
from pathlib import Path


def read_summary(root):
    rows = json.loads((root / "summary.json").read_text())
    return {str(row["seed"]): row for row in rows}


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(q * len(values)) - 1)] if values else None


def pooled_group(metrics):
    total = {"samples": 0, "speed_sum": 0.0, "distance_m": 0.0,
             "hard_brake_time_s": 0.0, "stop_time_s": 0.0}
    shortfall = []
    for item in metrics:
        for key in total:
            total[key] += item.get(key, 0)
        shortfall.extend(item.get("shortfall", []))
    return {**total,
            "mean_speed_mps": total["speed_sum"] / total["samples"] if total["samples"] else None,
            "hard_brake_rate": total["hard_brake_time_s"] / (total["samples"] * .1) if total["samples"] else None,
            "stop_rate": total["stop_time_s"] / (total["samples"] * .1) if total["samples"] else None,
            "free_flow_shortfall_m": {"count": len(shortfall),
                                        "mean": statistics.mean(shortfall) if shortfall else None,
                                        "median": percentile(shortfall, .5),
                                        "p95": percentile(shortfall, .95),
                                        "max": max(shortfall) if shortfall else None}}


def aggregate_prediction(items):
    total = {"windows": 0, "samples": 0, "absolute_error": 0.0,
             "squared_error": 0.0, "distance_error_m": 0.0, "followers": 0.0}
    for item in items:
        for key in total:
            total[key] += item.get(key, 0)
    if not total["samples"]:
        return {"windows": 0}
    return {"windows": total["windows"], "samples": total["samples"],
            "speed_mae_mps": total["absolute_error"] / total["samples"],
            "speed_rmse_mps": math.sqrt(total["squared_error"] / total["samples"]),
            "mean_abs_distance_error_m_per_window": total["distance_error_m"] / total["windows"],
            "mean_followers_per_window": total["followers"] / total["windows"]}


def raw_prediction(metrics, key):
    data = metrics.get("prediction_accuracy_raw", {}).get(key, {})
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline, proposal = read_summary(args.baseline), read_summary(args.proposal)
    seeds = sorted(set(baseline) & set(proposal), key=int)
    rows, baseline_metrics, proposal_metrics = [], [], []
    proposal_prediction = []
    proposal_counts = {}
    for seed in seeds:
        control, method = baseline[seed], proposal[seed]
        control_metric = json.loads((args.baseline / "eval3" / f"seed-{seed}" / "evaluation-metrics.json").read_text())
        method_metric = json.loads((args.proposal / "eval3" / f"seed-{seed}" / "evaluation-metrics.json").read_text())
        baseline_metrics.append(control_metric)
        proposal_metrics.append(method_metric)
        audit = json.loads((args.proposal / "eval3" / f"seed-{seed}" / "deceleration-audit.json").read_text())
        for name, value in audit["counts"].items():
            proposal_counts[name] = proposal_counts.get(name, 0) + value
        rows.append({"seed": int(seed), "tivtep_speed_mps": control["all_speed_mps"],
                     "proposal_speed_mps": method["all_speed_mps"],
                     "difference_mps": method["all_speed_mps"] - control["all_speed_mps"]})
        # Raw sums are included by the instrumented audit to support pooling.
        proposal_prediction.append(raw_prediction(method_metric, "all"))
    def groups(items, shortfall_key="vehicle_free_flow_shortfall_samples_m"):
        result = {}
        for group in ("car", "bus"):
            packed = []
            for metric in items:
                data = metric.get("groups", {}).get(group, {})
                packed.append({**data, "shortfall": metric.get(shortfall_key, {}).get(group, [])})
            result[group] = pooled_group(packed)
        return result

    def shortfall_distributions(items, key):
        """Pool only the requested vehicle-level loss samples across seeds."""
        result = {}
        for group in ("car", "bus"):
            values = []
            for metric in items:
                values.extend(metric.get(key, {}).get(group, []))
            result[group] = {"count": len(values),
                             "mean": statistics.mean(values) if values else None,
                             "median": percentile(values, .5),
                             "p95": percentile(values, .95),
                             "max": max(values) if values else None}
        return result
    differences = [row["difference_mps"] for row in rows]
    report = {"scope": "Eval.3, alpha=7, inflow=400/400/400, paper-random25, 600 s, paired seeds 1-5",
              "per_seed": rows,
              "speed": {"tivtep_mean_mps": statistics.mean(row["tivtep_speed_mps"] for row in rows),
                        "proposal_mean_mps": statistics.mean(row["proposal_speed_mps"] for row in rows),
                        "paired_difference_mean_mps": statistics.mean(differences),
                        "paired_difference_sample_sd_mps": statistics.stdev(differences)},
              "traffic_metrics": {"tivtep": groups(baseline_metrics), "proposal": groups(proposal_metrics)},
              "following_vehicle_shortfall": {"tivtep": shortfall_distributions(baseline_metrics, "following_vehicle_free_flow_shortfall_samples_m"),
                                               "proposal": shortfall_distributions(proposal_metrics, "following_vehicle_free_flow_shortfall_samples_m")},
              "proposal_prediction_accuracy": aggregate_prediction(proposal_prediction),
              "proposal_decision_counts": proposal_counts,
              "limitations": ["Prediction accuracy is observed only for the proposal-selected action; it is not a counterfactual outcome test.",
                              "The same-event TIV comparison counts decision disagreements, but cannot establish which alternative would have been better without branch replay.",
                              "Free-flow shortfall is a distributional proxy, not the proposal's counterfactual distance-loss definition."]}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2))
    lines = ["# Eval.3: TIVtep と減速伝播提案法の比較", "", report["scope"], "",
             "## 平均速度", "", "| 指標 | TIVtep | 提案法 | 差 |", "|---|---:|---:|---:|"]
    speed = report["speed"]
    lines.append(f"| 平均速度 [m/s] | {speed['tivtep_mean_mps']:.4f} | {speed['proposal_mean_mps']:.4f} | {speed['paired_difference_mean_mps']:+.4f} |")
    lines += ["", "## Seed別", "", "| seed | TIVtep | 提案法 | 差 |", "|---:|---:|---:|---:|"]
    lines += [f"| {row['seed']} | {row['tivtep_speed_mps']:.4f} | {row['proposal_speed_mps']:.4f} | {row['difference_mps']:+.4f} |" for row in rows]
    lines += ["", "## 計測済みの安全・分布指標", "", "JSONの `traffic_metrics`、`proposal_prediction_accuracy`、`proposal_decision_counts` をHTML化の一次データとする。", "", "## 限界", ""]
    lines += [f"- {item}" for item in report["limitations"]]
    (args.output / "evaluation-report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

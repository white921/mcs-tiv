#!/usr/bin/env python3

import argparse
import itertools
import json
import os
import subprocess
import sys
from copy import deepcopy

from compare_run_summaries import compare_summaries
from evaluate_run_summary import evaluate_summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run parameter sweeps for the cooperative ramp merge controller"
    )
    parser.add_argument(
        "--base-config",
        default=os.path.join(os.path.dirname(__file__), "controller_params.json"),
        help="Base controller parameter JSON",
    )
    parser.add_argument(
        "--sweep-config",
        default=os.path.join(os.path.dirname(__file__), "controller_sweep.json"),
        help="Sweep definition JSON",
    )
    parser.add_argument(
        "--output-dir",
        default="out/tuning",
        help="Directory for generated configs, summaries, and ranking output",
    )
    parser.add_argument(
        "--sumo-home",
        default=os.environ.get("SUMO_HOME", ""),
        help="SUMO_HOME to inject into child runs if needed",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable to use for child runs",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="How many top-ranked results to print in the final summary",
    )
    parser.add_argument(
        "--baseline-summary",
        help="Optional baseline run summary JSON used to build a composite ranking score",
    )
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def dump_json(path, payload):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)


def compute_ranking_score(evaluation, comparison_result=None):
    score = evaluation["paper_alignment_score"]
    if comparison_result is None:
        return round(score, 4)

    comparison = comparison_result["comparison"]
    score += 0.35 * comparison.get("paper_alignment_score_improvement", 0.0)
    score += 0.20 * comparison.get("mv2_speed_variance_improvement", 0.0)
    score += 0.15 * comparison.get("rv_speed_variance_improvement", 0.0)
    score += 0.10 * comparison.get("rv_advisory_mismatch_change", 0.0)
    return round(score, 4)


def iter_parameter_variants(base_config, sweep_config):
    parameter_grid = sweep_config.get("parameters", {})
    parameter_names = sorted(parameter_grid.keys())
    parameter_values = [parameter_grid[name] for name in parameter_names]

    variant_id = 0
    for combination in itertools.product(*parameter_values):
        variant = deepcopy(base_config)
        applied = {}
        for name, value in zip(parameter_names, combination):
            variant[name] = value
            applied[name] = value
        yield variant_id, applied, variant
        variant_id += 1


def run_variant(args, variant_id, applied_params, variant_config, baseline_summary=None):
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    config_path = os.path.join(output_dir, f"controller_params_variant_{variant_id:03d}.json")
    summary_path = os.path.join(output_dir, f"run_summary_variant_{variant_id:03d}.json")
    stdout_path = os.path.join(output_dir, f"run_log_variant_{variant_id:03d}.txt")
    dump_json(config_path, variant_config)

    control_script = os.path.join(os.path.dirname(__file__), "control.py")
    cmd = [
        args.python_bin,
        control_script,
        "--nogui",
        "--controller-config",
        config_path,
        "--summary-json",
        summary_path,
    ]

    env = os.environ.copy()
    if args.sumo_home:
        env["SUMO_HOME"] = args.sumo_home

    with open(stdout_path, "w", encoding="utf-8") as stdout_file:
        completed = subprocess.run(
            cmd,
            stdout=stdout_file,
            stderr=subprocess.STDOUT,
            env=env,
            check=False,
        )

    if completed.returncode != 0:
        return {
            "variant_id": variant_id,
            "status": "failed",
            "returncode": completed.returncode,
            "applied_params": applied_params,
            "config_path": config_path,
            "summary_path": summary_path,
            "log_path": stdout_path,
        }

    summary = load_json(summary_path)
    evaluation = evaluate_summary(summary)
    comparison_result = None
    if baseline_summary is not None:
        comparison_result = compare_summaries(summary, baseline_summary)
    ranking_score = compute_ranking_score(evaluation, comparison_result)
    return {
        "variant_id": variant_id,
        "status": "ok",
        "applied_params": applied_params,
        "config_path": config_path,
        "summary_path": summary_path,
        "log_path": stdout_path,
        "evaluation": evaluation,
        "comparison_to_baseline": comparison_result,
        "ranking_score": ranking_score,
    }


def main():
    args = parse_args()
    base_config = load_json(args.base_config)
    sweep_config = load_json(args.sweep_config)
    baseline_summary = load_json(args.baseline_summary) if args.baseline_summary else None

    results = []
    for variant_id, applied_params, variant_config in iter_parameter_variants(
        base_config, sweep_config
    ):
        print(f"running variant {variant_id:03d} with {applied_params}", flush=True)
        result = run_variant(
            args, variant_id, applied_params, variant_config, baseline_summary=baseline_summary
        )
        results.append(result)

    output_dir = os.path.abspath(args.output_dir)
    ranking_path = os.path.join(output_dir, "ranking.json")
    dump_json(ranking_path, results)

    successful = [result for result in results if result["status"] == "ok"]
    successful.sort(
        key=lambda item: item.get("ranking_score", item["evaluation"]["paper_alignment_score"]),
        reverse=True,
    )

    print(f"saved ranking to {ranking_path}")
    if not successful:
        print("no successful runs")
        return

    print("top results:")
    for result in successful[: args.top_k]:
        print(
            f"variant={result['variant_id']:03d} "
            f"score={result['ranking_score']:.4f} "
            f"params={result['applied_params']} "
            f"deltas={result['evaluation']['deltas']}"
        )


if __name__ == "__main__":
    main()

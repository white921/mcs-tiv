#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a coarse-to-fine tuning pipeline for the cooperative ramp merge controller"
    )
    parser.add_argument(
        "--base-config",
        default=os.path.join(SCRIPT_DIR, "controller_params.json"),
        help="Base controller parameter JSON for round 1",
    )
    parser.add_argument(
        "--sweep-config",
        default=os.path.join(SCRIPT_DIR, "controller_sweep.json"),
        help="Initial sweep definition JSON",
    )
    parser.add_argument(
        "--output-dir",
        default="out/auto_tuning",
        help="Root output directory for all rounds",
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
        help="How many top-ranked results each tune step should print",
    )
    parser.add_argument(
        "--refinement-rounds",
        type=int,
        default=1,
        help="How many refine-and-retune rounds to run after the initial sweep",
    )
    parser.add_argument(
        "--top-index",
        type=int,
        default=0,
        help="Which ranked successful result to refine around each round",
    )
    parser.add_argument(
        "--shrink-factor",
        type=float,
        default=0.5,
        help="Scale factor for numeric sweep step sizes during refinement",
    )
    parser.add_argument(
        "--baseline-summary",
        help="Optional baseline run summary JSON used for composite ranking",
    )
    parser.add_argument(
        "--baseline-config",
        default=os.path.join(SCRIPT_DIR, "..", "cfg", "ramp.sumocfg"),
        help="SUMO config path used when auto-generating a baseline summary",
    )
    parser.add_argument(
        "--focus-round",
        action="store_true",
        help="Run one additional focused fine-tuning round around the best refined configuration",
    )
    return parser.parse_args()


def run_cmd(cmd, env):
    completed = subprocess.run(cmd, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def dump_json(path, payload):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)


def top_successful_result(ranking_path):
    ranking = load_json(ranking_path)
    successful = [result for result in ranking if result.get("status") == "ok"]
    successful.sort(
        key=lambda item: item.get("ranking_score", item["evaluation"]["paper_alignment_score"]),
        reverse=True,
    )
    if not successful:
        raise SystemExit(f"No successful results found in {ranking_path}")
    return successful[0]


def ensure_baseline_summary(args, env, output_root):
    if args.baseline_summary:
        return args.baseline_summary

    baseline_script = os.path.join(SCRIPT_DIR, "baseline_log.py")
    baseline_summary_path = os.path.join(output_root, "baseline_summary.json")
    print(f"generating baseline summary at {baseline_summary_path}", flush=True)
    run_cmd(
        [
            args.python_bin,
            baseline_script,
            "--config",
            args.baseline_config,
            "--summary-json",
            baseline_summary_path,
        ],
        env,
    )
    return baseline_summary_path


def main():
    args = parse_args()
    env = os.environ.copy()
    if args.sumo_home:
        env["SUMO_HOME"] = args.sumo_home

    output_root = os.path.abspath(args.output_dir)
    os.makedirs(output_root, exist_ok=True)
    baseline_summary = ensure_baseline_summary(args, env, output_root)

    tune_script = os.path.join(SCRIPT_DIR, "tune_controller.py")
    refine_script = os.path.join(SCRIPT_DIR, "refine_tuning.py")
    focus_script = os.path.join(SCRIPT_DIR, "generate_focus_sweep.py")

    round1_dir = os.path.join(output_root, "round1")
    print(f"starting round1 in {round1_dir}", flush=True)
    round1_cmd = [
        args.python_bin,
        tune_script,
        "--base-config",
        args.base_config,
        "--sweep-config",
        args.sweep_config,
        "--output-dir",
        round1_dir,
        "--python-bin",
        args.python_bin,
        "--top-k",
        str(args.top_k),
        "--sumo-home",
        args.sumo_home,
    ]
    if baseline_summary:
        round1_cmd.extend(["--baseline-summary", baseline_summary])
    run_cmd(round1_cmd, env)

    current_ranking = os.path.join(round1_dir, "ranking.json")
    current_sweep = args.sweep_config

    for round_index in range(1, args.refinement_rounds + 1):
        refine_dir = os.path.join(output_root, f"refined_round{round_index}")
        run_dir = os.path.join(output_root, f"round{round_index + 1}")

        print(f"refining around {current_ranking} into {refine_dir}", flush=True)
        run_cmd(
            [
                args.python_bin,
                refine_script,
                current_ranking,
                "--sweep-config",
                current_sweep,
                "--output-dir",
                refine_dir,
                "--top-index",
                str(args.top_index),
                "--shrink-factor",
                str(args.shrink_factor),
            ],
            env,
        )

        refined_base = os.path.join(refine_dir, "controller_params_refined_base.json")
        refined_sweep = os.path.join(refine_dir, "controller_sweep_refined.json")

        print(f"starting round{round_index + 1} in {run_dir}", flush=True)
        round_cmd = [
            args.python_bin,
            tune_script,
            "--base-config",
            refined_base,
            "--sweep-config",
            refined_sweep,
            "--output-dir",
            run_dir,
            "--python-bin",
            args.python_bin,
            "--top-k",
            str(args.top_k),
            "--sumo-home",
            args.sumo_home,
        ]
        if baseline_summary:
            round_cmd.extend(["--baseline-summary", baseline_summary])
        run_cmd(round_cmd, env)

        current_ranking = os.path.join(run_dir, "ranking.json")
        current_sweep = refined_sweep

    if args.focus_round:
        best_before_focus = top_successful_result(current_ranking)
        focus_dir = os.path.join(output_root, "focus_round")
        os.makedirs(focus_dir, exist_ok=True)
        focus_sweep = os.path.join(focus_dir, "controller_sweep_focus.json")
        print(f"generating focused sweep from {best_before_focus['config_path']}", flush=True)
        run_cmd(
            [
                args.python_bin,
                focus_script,
                best_before_focus["config_path"],
                "--output",
                focus_sweep,
            ],
            env,
        )

        focus_run_dir = os.path.join(output_root, "round_focus")
        print(f"starting focused round in {focus_run_dir}", flush=True)
        focus_cmd = [
            args.python_bin,
            tune_script,
            "--base-config",
            best_before_focus["config_path"],
            "--sweep-config",
            focus_sweep,
            "--output-dir",
            focus_run_dir,
            "--python-bin",
            args.python_bin,
            "--top-k",
            str(args.top_k),
            "--sumo-home",
            args.sumo_home,
        ]
        if baseline_summary:
            focus_cmd.extend(["--baseline-summary", baseline_summary])
        run_cmd(focus_cmd, env)
        current_ranking = os.path.join(focus_run_dir, "ranking.json")

    best = top_successful_result(current_ranking)
    best_config = load_json(best["config_path"])
    best_config_path = os.path.join(output_root, "best_controller_params.json")
    best_result_path = os.path.join(output_root, "best_result.json")
    dump_json(best_config_path, best_config)
    dump_json(best_result_path, best)
    print("final best result:")
    print(
        f"variant={best['variant_id']:03d} "
        f"score={best.get('ranking_score', best['evaluation']['paper_alignment_score']):.4f} "
        f"params={best['applied_params']} "
        f"deltas={best['evaluation']['deltas']} "
        f"config={best['config_path']}"
    )
    print(f"saved best config to {best_config_path}")
    print(f"saved best result to {best_result_path}")


if __name__ == "__main__":
    main()

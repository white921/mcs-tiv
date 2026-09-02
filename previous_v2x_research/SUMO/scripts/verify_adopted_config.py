#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run cooperative and baseline verification for the adopted controller config"
    )
    parser.add_argument(
        "--controller-config",
        default=os.path.join(SCRIPT_DIR, "controller_params.json"),
        help="Controller parameter JSON to verify",
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
        "--output-dir",
        default="out/verification",
        help="Directory for cooperative/baseline summaries and comparison output",
    )
    parser.add_argument(
        "--config",
        default=os.path.join(PROJECT_ROOT, "cfg", "ramp.sumocfg"),
        help="SUMO config path",
    )
    return parser.parse_args()


def run_cmd(cmd, env, stdout_path=None):
    if stdout_path:
        with open(stdout_path, "w", encoding="utf-8") as stdout_file:
            completed = subprocess.run(
                cmd,
                stdout=stdout_file,
                stderr=subprocess.STDOUT,
                env=env,
                check=False,
            )
    else:
        completed = subprocess.run(cmd, env=env, check=False)

    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main():
    args = parse_args()
    env = os.environ.copy()
    if args.sumo_home:
        env["SUMO_HOME"] = args.sumo_home

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    control_script = os.path.join(SCRIPT_DIR, "control.py")
    baseline_script = os.path.join(SCRIPT_DIR, "baseline_log.py")
    compare_script = os.path.join(SCRIPT_DIR, "compare_run_summaries.py")

    cooperative_summary = os.path.join(output_dir, "cooperative_summary.json")
    baseline_summary = os.path.join(output_dir, "baseline_summary.json")
    comparison_log = os.path.join(output_dir, "comparison.txt")

    print("running cooperative verification", flush=True)
    run_cmd(
        [
            args.python_bin,
            control_script,
            "--nogui",
            "--config",
            args.config,
            "--controller-config",
            args.controller_config,
            "--summary-json",
            cooperative_summary,
        ],
        env,
        stdout_path=os.path.join(output_dir, "cooperative_run.txt"),
    )

    print("running baseline verification", flush=True)
    run_cmd(
        [
            args.python_bin,
            baseline_script,
            "--config",
            args.config,
            "--summary-json",
            baseline_summary,
        ],
        env,
        stdout_path=os.path.join(output_dir, "baseline_run.txt"),
    )

    print("comparing cooperative and baseline summaries", flush=True)
    run_cmd(
        [
            args.python_bin,
            compare_script,
            cooperative_summary,
            baseline_summary,
        ],
        env,
        stdout_path=comparison_log,
    )

    print(f"saved cooperative summary to {cooperative_summary}")
    print(f"saved baseline summary to {baseline_summary}")
    print(f"saved comparison report to {comparison_log}")


if __name__ == "__main__":
    main()

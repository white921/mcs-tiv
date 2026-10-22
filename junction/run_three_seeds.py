#!/usr/bin/env python3
"""Run the T-junction experiment for several seeds and report the mean speed."""

import argparse
import math
import os
import re
import signal
import statistics
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RUNNER = SCRIPT_DIR / "junction_three_agree.py"
ALL_SPEED_PATTERN = re.compile(r"^all_speed\s*:\s*(\S+)\s*$", re.MULTILINE)
VEHICLE_MIX_PATTERN = re.compile(
    r"^vehicle_mix\s*:\s*Bus\s+(\d+)\s+Car\s+(\d+)\s+bus_rate\s+(\S+)%\s*$",
    re.MULTILINE,
)
PROGRESS_PATTERN = re.compile(r"^TIME:\s+(\d+(?:\.\d+)?)")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run junction_three_agree.py for multiple random seeds."
    )
    parser.add_argument("alpha", help="TIV method parameter, e.g. 7 for TIVtep")
    parser.add_argument("inflow_left", type=int)
    parser.add_argument("inflow_bottom", type=int)
    parser.add_argument("inflow_right", type=int)
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--bus-share", type=float, default=0.25)
    parser.add_argument(
        "--bus-allocation",
        choices=["fixed", "paper-random25"],
        default="fixed",
    )
    parser.add_argument("--route-mode", choices=["random", "eval1"], default="random")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument(
        "--reference-speed",
        type=float,
        help="optional paper value used to show the difference from the seed mean",
    )
    args = parser.parse_args()
    if not 0 <= args.bus_share <= 1:
        parser.error("--bus-share must be between 0 and 1")
    return args


def parse_run_summary(output, seed):
    speed_match = ALL_SPEED_PATTERN.search(output)
    mix_match = VEHICLE_MIX_PATTERN.search(output)
    if speed_match is None or mix_match is None:
        raise RuntimeError(f"could not parse summary for seed {seed}")
    return {
        "seed": seed,
        "speed": float(speed_match.group(1)),
        "buses": int(mix_match.group(1)),
        "cars": int(mix_match.group(2)),
        "bus_rate": float(mix_match.group(3)),
    }


def run_seed(command, seed, duration):
    print(f"seed {seed}: starting", flush=True)
    process = subprocess.Popen(
        command,
        cwd=SCRIPT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    output_lines = []
    try:
        assert process.stdout is not None
        for line in process.stdout:
            output_lines.append(line)
            progress_match = PROGRESS_PATTERN.match(line)
            if progress_match is not None:
                simulation_time = float(progress_match.group(1))
                print(
                    f"\rseed {seed}: {simulation_time:g}/{duration:g} simulation seconds",
                    end="",
                    flush=True,
                )
        return_code = process.wait()
    except KeyboardInterrupt:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        print(f"\nseed {seed}: stopped", file=sys.stderr)
        raise SystemExit(130)

    print()
    output = "".join(output_lines)
    if return_code != 0:
        print(output, file=sys.stderr)
        raise SystemExit(f"seed {seed} failed with exit code {return_code}")
    return output


def main():
    args = parse_args()
    results = []

    for seed in args.seeds:
        command = [
            sys.executable,
            str(RUNNER),
            args.alpha,
            str(seed),
            str(args.inflow_left),
            str(args.inflow_bottom),
            str(args.inflow_right),
            "--nogui",
            "--quiet",
            "--duration",
            str(args.duration),
            "--bus-share",
            str(args.bus_share),
            "--bus-allocation",
            args.bus_allocation,
            "--route-mode",
            args.route_mode,
        ]
        if args.no_save:
            command.append("--no-save")
        output = run_seed(command, seed, args.duration)
        result = parse_run_summary(output, seed)
        results.append(result)
        print(
            f"seed {seed}: all_speed={result['speed']:.4f} m/s, "
            f"Bus={result['buses']}, Car={result['cars']}, "
            f"bus_rate={result['bus_rate']:.2f}%"
        )

    finite_speeds = [result["speed"] for result in results if math.isfinite(result["speed"])]
    if len(finite_speeds) != len(results):
        raise SystemExit("one or more runs produced a non-finite all_speed")

    mean_speed = statistics.fmean(finite_speeds)
    print(f"seed mean: {mean_speed:.4f} m/s")
    if args.reference_speed is not None:
        difference = mean_speed - args.reference_speed
        percent = difference / args.reference_speed * 100
        print(
            f"reference: {args.reference_speed:.4f} m/s, "
            f"difference: {difference:+.4f} m/s ({percent:+.2f}%)"
        )


if __name__ == "__main__":
    main()

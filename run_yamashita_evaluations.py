#!/usr/bin/env python3
"""Run or inspect the Chapter 5 evaluation matrix without changing source data."""

import argparse
import csv
import math
import re
import shlex
import statistics
import subprocess
import sys
from pathlib import Path

from thesis_evaluations import EVALUATIONS, METHOD_ALPHA


ROOT = Path(__file__).resolve().parent
ALL_SPEED_PATTERN = re.compile(r"^all_speed\s*:\s*(\S+)\s*$", re.MULTILINE)
VEHICLE_MIX_PATTERN = re.compile(
    r"^vehicle_mix\s*:\s*Bus\s+(\d+)\s+Car\s+(\d+)\s+bus_rate\s+(\S+)%\s*$",
    re.MULTILINE,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evaluations",
        nargs="+",
        choices=tuple(EVALUATIONS),
        default=list(EVALUATIONS),
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        help="override the documented default seed set for every selected evaluation",
    )
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument(
        "--bus-allocation",
        choices=("fixed", "paper-random25"),
        default="fixed",
        help="fixed matches the stated ratio; paper-random25 matches the original artifact's draw",
    )
    parser.add_argument("--output-root", type=Path, default=ROOT / "results" / "yamashita")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print commands only; do not start SUMO or create result files",
    )
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be greater than 0")
    return args


def build_command(evaluation, method, inflows, seed, duration, bus_allocation):
    script = ROOT / evaluation.scenario
    command = [
        sys.executable,
        str(script),
        str(METHOD_ALPHA[method]),
        str(seed),
        *map(str, inflows),
        "--nogui",
        "--quiet",
        "--duration",
        str(duration),
        "--bus-share",
        str(evaluation.bus_share),
        "--bus-allocation",
        bus_allocation,
        "--no-save",
    ]
    if evaluation.route_mode is not None:
        command.extend(("--route-mode", evaluation.route_mode))
    return command


def parse_summary(output, label):
    speed_match = ALL_SPEED_PATTERN.search(output)
    mix_match = VEHICLE_MIX_PATTERN.search(output)
    if speed_match is None or mix_match is None:
        raise RuntimeError(f"could not parse simulation summary for {label}")
    speed = float(speed_match.group(1))
    if not math.isfinite(speed):
        raise RuntimeError(f"non-finite all_speed for {label}: {speed}")
    return speed, int(mix_match.group(1)), int(mix_match.group(2)), float(mix_match.group(3))


def run_one(command, label):
    print(f"{label}: starting", flush=True)
    completed = subprocess.run(
        command,
        cwd=Path(command[1]).parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code {completed.returncode}:\n{completed.stdout}"
        )
    return parse_summary(completed.stdout, label)


def write_results(output_root, run_rows, comparison_rows):
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("evaluation", "method", "inflows", "seed", "all_speed_mps", "buses", "cars", "bus_rate_percent")
        )
        writer.writerows(run_rows)
    with (output_root / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("evaluation", "method", "inflows", "seeds", "mean_mps", "thesis_mps", "difference_mps")
        )
        writer.writerows(comparison_rows)


def main():
    args = parse_args()
    run_rows = []
    comparison_rows = []
    command_count = 0

    for evaluation_name in args.evaluations:
        evaluation = EVALUATIONS[evaluation_name]
        seeds = tuple(args.seeds) if args.seeds is not None else evaluation.default_seeds
        for condition in evaluation.conditions:
            inflows_text = "/".join(map(str, condition.inflows))
            for method, reference in zip(evaluation.methods, condition.references):
                speeds = []
                for seed in seeds:
                    command = build_command(
                        evaluation,
                        method,
                        condition.inflows,
                        seed,
                        args.duration,
                        args.bus_allocation,
                    )
                    command_count += 1
                    label = f"{evaluation_name} {method} {inflows_text} seed {seed}"
                    if args.dry_run:
                        print(f"{label}: {shlex.join(command)}")
                        continue
                    speed, buses, cars, bus_rate = run_one(command, label)
                    speeds.append(speed)
                    run_rows.append(
                        (evaluation_name, method, inflows_text, seed, speed, buses, cars, bus_rate)
                    )

                if args.dry_run:
                    continue
                mean_speed = statistics.fmean(speeds)
                difference = "" if reference is None else mean_speed - reference
                comparison_rows.append(
                    (
                        evaluation_name,
                        method,
                        inflows_text,
                        " ".join(map(str, seeds)),
                        mean_speed,
                        "" if reference is None else reference,
                        difference,
                    )
                )
                reference_text = "not reported" if reference is None else f"{reference:.4f} m/s"
                print(
                    f"{evaluation_name} {method} {inflows_text}: "
                    f"mean={mean_speed:.4f} m/s, thesis={reference_text}",
                    flush=True,
                )

    if args.dry_run:
        print(f"planned runs: {command_count}")
        return
    write_results(args.output_root, run_rows, comparison_rows)
    print(f"wrote {args.output_root / 'runs.csv'}")
    print(f"wrote {args.output_root / 'comparison.csv'}")


if __name__ == "__main__":
    main()

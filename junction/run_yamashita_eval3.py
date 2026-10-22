#!/usr/bin/env python3
"""Reproduce Table 5.7 and Table 5.8 from Yamashita's thesis.

The experiment is the T-intersection evaluation with a 25% CAVbus share,
600 seconds of simulation, and five independently seeded runs per condition.
"""

import argparse
import re
import statistics
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RUNNER = SCRIPT_DIR / "junction_three_agree.py"
SPEED_PATTERN = re.compile(r"^all_speed\s*:\s*(\S+)$", re.MULTILINE)

METHODS = {
    "ALW": (1, 6.6075, 4.6017),
    "ACT": (2, 6.6722, 4.8419),
    "SPD40": (4, 7.3775, 5.9591),
    "UTF": (5, 6.8242, 5.5058),
    "TIVte": (6, 7.3584, 6.1898),
    "TIVtep": (7, 7.4159, 6.4955),
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inflows", type=int, nargs="+", default=[400, 500],
        help="per-approach inflows to reproduce (default: 400 500)",
    )
    parser.add_argument(
        "--methods", nargs="+", choices=METHODS, default=list(METHODS),
        help="methods to run (default: all methods in Tables 5.7 and 5.8)",
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    return parser.parse_args()


def run_once(alpha, seed, inflow):
    command = [
        sys.executable, str(RUNNER), str(alpha), str(seed), str(inflow),
        str(inflow), str(inflow), "--nogui", "--quiet",
    ]
    completed = subprocess.run(
        command, cwd=SCRIPT_DIR, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"alpha={alpha}, seed={seed} failed:\n{completed.stdout}")
    match = SPEED_PATTERN.search(completed.stdout)
    if match is None:
        raise RuntimeError(f"no all_speed summary for alpha={alpha}, seed={seed}")
    return float(match.group(1))


def main():
    args = parse_args()
    for inflow in args.inflows:
        if inflow not in (400, 500):
            raise SystemExit("the thesis reference values are available only for inflows 400 and 500")
        reference_index = 1 if inflow == 400 else 2
        print(f"\nEval.3: {inflow} vehicles/h per approach, bus share 25%")
        print("method, alpha, seed_mean_mps, thesis_mps, difference_mps")
        for name in args.methods:
            alpha, paper_400, paper_500 = METHODS[name]
            speeds = [run_once(alpha, seed, inflow) for seed in args.seeds]
            measured = statistics.fmean(speeds)
            reference = (paper_400, paper_500)[reference_index - 1]
            print(f"{name}, {alpha}, {measured:.4f}, {reference:.4f}, {measured - reference:+.4f}")


if __name__ == "__main__":
    main()

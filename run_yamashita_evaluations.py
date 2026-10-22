#!/usr/bin/env python3
"""Run every thesis condition reported in Tables 5.4, 5.6--5.8 and 5.10--5.15.

Each condition is executed once for every requested seed.  The script writes
the per-seed results and their mean to a CSV file, alongside the corresponding
average speed reported in the thesis where available.
"""

import argparse
import concurrent.futures
import csv
import os
import re
import statistics
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / "scripts" / "run_sumo.sh"
SPEED = re.compile(r"^all_speed\s*:\s*(\S+)$", re.MULTILINE)
METHODS = {"ALW": 1, "ACT": 2, "SPD20": 3, "SPD40": 4, "UTF": 5, "TIVte": 6, "TIVtep": 7}

# Reference values are the Total/Average rows in the thesis tables.
EVALUATIONS = {
    "eval1": ("junction/junction_three_agree.py", 0, "eval1", ["ALW", "ACT", "SPD40", "UTF", "TIVte"],
              [(660, 180, 660), (630, 240, 630), (600, 300, 600), (570, 360, 570), (540, 420, 540)],
              [[11.1658, 8.6829, 11.2717, 11.1541, 11.7161], [9.5198, 7.7905, 10.2397, 10.1473, 11.0795], [9.0798, 7.2777, 9.3689, 8.7589, 10.1818], [7.4911, 6.2621, 8.0755, 8.1436, 9.2596], [7.1264, 5.6751, 6.5737, 7.5179, 8.8924]]),
    "eval2": ("junction/junction_three_agree.py", 0, "random", ["ALW", "ACT", "SPD20", "UTF", "TIVte"],
              [(400, 400, 400), (500, 500, 500), (600, 600, 600)],
              [[7.1926, 7.2162, 7.8629, 7.5538, 7.8222], [4.0510, 5.6945, 6.5408, 5.6555, 7.2766], [2.6919, 3.4965, 3.7923, 3.3530, 3.7233]]),
    "eval3": ("junction/junction_three_agree.py", .25, "random", ["ALW", "ACT", "SPD40", "UTF", "TIVte", "TIVtep"],
              [(400, 400, 400), (500, 500, 500)],
              [[6.6075, 6.6722, 7.3775, 6.8242, 7.3584, 7.4159], [4.6017, 4.8419, 5.9591, 5.5058, 6.1898, 6.4955]]),
    "eval4": ("junction/junction_four_agree.py", 0, None, ["ALW", "ACT", "SPD40", "UTF", "TIVte"],
              [(300, 300, 300, 300), (400, 400, 400, 400)],
              [[5.8631, 6.5145, 6.8127, 6.8077, 7.2485], [3.6997, 4.1850, 4.5090, 4.3336, 4.5560]]),
    "eval5": ("junction/junction_four_agree.py", .25, None, ["ALW", "ACT", "SPD20", "UTF", "TIVte", "TIVtep"],
              [(300, 300, 300, 300)], [[5.3037, 5.6246, 5.5534, 5.8622, 6.2789, 6.4420]]),
    "eval6": ("merge/merge_agree2512.py", 0, None, ["ALW", "ACT", "SPD40", "UTF", "TIVte"],
              [(800, 1200), (1000, 1000), (1200, 800)],
              [[4.0606, 3.9883, 4.2267, 4.5430, 4.4439], [4.1118, 3.7198, 3.8212, 4.3100, 4.8032], [4.7338, 3.4712, 3.8368, 4.7447, 4.6601]]),
    "eval7": ("merge/merge_agree2512.py", .25, None, ["ALW", "ACT", "SPD40", "UTF", "TIVte", "TIVtep"],
              [(1000, 1000)], [[4.2685, 3.3895, 3.6235, 4.3664, 4.2724, 4.2084]]),
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluations", nargs="+", choices=EVALUATIONS, default=list(EVALUATIONS))
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--output-root", type=Path, default=ROOT / "results" / "yamashita")
    parser.add_argument("--workers", type=int, default=min(12, os.cpu_count() or 1), help="number of independent SUMO runs to execute concurrently")
    parser.add_argument("--stage-one", action="store_true", help="run only seed 1 for every reported condition, writing to results/yamashita-stage1 by default")
    return parser.parse_args()


def run_one(scenario, bus_share, route_mode, alpha, seed, inflows, output_dir):
    command = ["bash", str(LAUNCHER), scenario, str(alpha), str(seed), *map(str, inflows), "--nogui", "--quiet", "--bus-share", str(bus_share), "--output-dir", str(output_dir)]
    if route_mode is not None:
        command += ["--route-mode", route_mode]
    completed = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.returncode:
        raise RuntimeError(f"{' '.join(command)} failed:\n{completed.stdout}")
    match = SPEED.search(completed.stdout)
    if match is None:
        raise RuntimeError(f"all_speed was not produced:\n{completed.stdout}")
    return float(match.group(1))


def run_condition(job):
    evaluation, scenario, bus_share, route_mode, method, inflows, reference, seeds, output_root = job
    values = []
    for seed in seeds:
        output = output_root / evaluation / method / "-".join(map(str, inflows)) / f"seed-{seed}"
        values.append(run_one(scenario, bus_share, route_mode, METHODS[method], seed, inflows, output))
    measured = statistics.fmean(values)
    return [evaluation, method, "/".join(map(str, inflows)), *values, measured, reference, measured - reference]


def main():
    args = parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    if args.stage_one:
        args.seeds = [1]
        if args.output_root == ROOT / "results" / "yamashita":
            args.output_root = ROOT / "results" / "yamashita-stage1"
    args.output_root.mkdir(parents=True, exist_ok=True)
    jobs = []
    for evaluation in args.evaluations:
        scenario, bus_share, route_mode, methods, inflows_list, references = EVALUATIONS[evaluation]
        for inflows, expected in zip(inflows_list, references):
            for method, reference in zip(methods, expected):
                jobs.append((evaluation, scenario, bus_share, route_mode, method, inflows, reference, args.seeds, args.output_root))
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for future in concurrent.futures.as_completed([executor.submit(run_condition, job) for job in jobs]):
            row = future.result()
            rows.append(row)
            print(f"{row[0]} {row[1]} {row[2]}: {row[-3]:.4f} (thesis {row[-2]:.4f}, diff {row[-1]:+.4f})", flush=True)
    rows.sort(key=lambda row: (row[0], row[2], row[1]))
    columns = ["evaluation", "method", "inflows", *[f"seed_{seed}" for seed in args.seeds], "mean_mps", "thesis_mps", "difference_mps"]
    with (args.output_root / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([columns, *rows])


if __name__ == "__main__":
    main()

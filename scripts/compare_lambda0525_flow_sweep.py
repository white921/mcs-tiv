#!/usr/bin/env python3
"""Add paired control comparisons to a lambda=0.525 flow-sweep summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import statistics
import subprocess


CONTROLS = {
    300: {
        "yamashita": ("7b48a0048", "results/runs/eval7-300-1000-yamashita-seeds33-42-600s-20261109T1200/summary.json"),
        "utf": ("98504479a", "results/runs/eval7-300-1000-utf-seeds33-42-600s-20261109T1200/summary.json"),
    },
    500: {
        "yamashita": ("262b049bb", "results/runs/eval7-500-1000-yamashita-seeds43-47-600s-20261109T/summary.json"),
        "utf": ("831aa145c", "results/runs/eval7-500-1000-utf-seeds43-47-600s-20261109T/summary.json"),
    },
    700: {
        "yamashita": ("b2d7afdc2", "results/runs/eval7-700-1000-yamashita-seeds33-42-600s-20261107T/summary.json"),
        "utf": ("708f3e985", "results/runs/eval7-700-1000-utf-seeds33-42-600s-20261108T/summary.json"),
    },
    1000: {
        "yamashita": ("8297d943a", "results/runs/normalized-convex-600s-yamashita-eval7-r1000-a1000-seeds33-42-20261115/summary.json"),
        "utf": ("30acd3eda", "results/runs/eval7-1000-1000-utf-seeds33-42-600s-20261109T1800/summary.json"),
    },
    1200: {
        "yamashita": ("cb3157005", "results/runs/eval7-1200-1000-yamashita-seeds33-42-600s-20261110T1200/summary.json"),
        "utf": ("c17f9d89d", "results/runs/eval7-1200-1000-utf-seeds33-42-600s-20261110T1200/summary.json"),
    },
}
LAMBDA_SUMMARY = (
    "6e38c226",
    "results/runs/normalized-convex-lambda0525-eval7-r1000-a1000-"
    "seeds33-42-600s-20261119/lambda-fine-sweep-summary.json",
)


def git_json(repo: Path, commit: str, path: str):
    raw = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(raw)


def compact(row: dict[str, object]) -> dict[str, object]:
    return {
        "seed": int(row["seed"]),
        "all_speed_mps": float(row["all_speed_mps"]),
        "fixed_input_sha256": row.get("fixed_input_sha256")
        or row.get("fixed_vehicle_input", {}).get("sha256"),
        "source_commit": row.get("git", {}).get("commit"),
    }


def bootstrap(differences: list[float], *, seed: int) -> list[float]:
    rng = random.Random(seed)
    samples = sorted(
        sum(differences[rng.randrange(len(differences))] for _ in differences)
        / len(differences)
        for _ in range(200_000)
    )
    return [samples[4_999], samples[194_999]]


def compare(
    proposal: list[dict[str, object]],
    control: list[dict[str, object]],
    *,
    bootstrap_seed: int,
) -> dict[str, object]:
    proposal_by_seed = {int(row["seed"]): row for row in proposal}
    control_by_seed = {int(row["seed"]): row for row in control}
    if set(proposal_by_seed) != set(control_by_seed):
        raise RuntimeError("proposal/control seed sets differ")
    seeds = sorted(proposal_by_seed)
    fixed_inputs_match = all(
        proposal_by_seed[seed]["fixed_input_sha256"]
        == control_by_seed[seed]["fixed_input_sha256"]
        for seed in seeds
    )
    if not fixed_inputs_match:
        raise RuntimeError("proposal/control fixed-input hashes differ")
    differences = [
        float(proposal_by_seed[seed]["all_speed_mps"])
        - float(control_by_seed[seed]["all_speed_mps"])
        for seed in seeds
    ]
    return {
        "seed_count": len(seeds),
        "fixed_inputs_match": True,
        "proposal_all_speed_mean_mps": statistics.mean(
            float(proposal_by_seed[seed]["all_speed_mps"]) for seed in seeds
        ),
        "control_all_speed_mean_mps": statistics.mean(
            float(control_by_seed[seed]["all_speed_mps"]) for seed in seeds
        ),
        "proposal_minus_control_mean_mps": statistics.mean(differences),
        "proposal_higher_seed_count": sum(value > 0 for value in differences),
        "paired_percentile_bootstrap_95_ci_mps": bootstrap(
            differences, seed=bootstrap_seed
        ),
        "control_source_commits": sorted(
            {str(row["source_commit"]) for row in control if row["source_commit"]}
        ),
        "per_seed_difference_mps": [
            {"seed": seed, "difference_mps": difference}
            for seed, difference in zip(seeds, differences, strict=True)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.summary.read_text())
    proposal_by_flow = {
        flow: [
            compact(row)
            for row in report["per_seed"]
            if int(row["flow_requesting_vph"]) == flow
        ]
        for flow in (300, 500, 700, 1200)
    }
    fine = git_json(args.repo, *LAMBDA_SUMMARY)
    proposal_by_flow[1000] = [
        compact(row) for row in fine["per_seed"] if float(row["lambda"]) == 0.525
    ]
    comparisons = {}
    control_references = {}
    for flow, methods in CONTROLS.items():
        comparisons[str(flow)] = {}
        control_references[str(flow)] = {}
        for method_index, (method, (commit, path)) in enumerate(methods.items()):
            control = [compact(row) for row in git_json(args.repo, commit, path)]
            comparisons[str(flow)][method] = compare(
                proposal_by_flow[flow],
                control,
                bootstrap_seed=20261122 + flow * 10 + method_index,
            )
            control_references[str(flow)][method] = {
                "result_commit": commit,
                "summary_path": path,
            }
    report["reused_1000"] = {
        "result_commit": LAMBDA_SUMMARY[0],
        "summary_path": LAMBDA_SUMMARY[1],
        "aggregate": fine["aggregates"]["0.525"],
        "per_seed": proposal_by_flow[1000],
    }
    report["control_references"] = control_references
    report["flow_comparisons"] = comparisons
    report["comparison_notes"] = {
        "bootstrap_resamples": 200_000,
        "difference_direction": "lambda0525 minus control",
        "development_not_independent_holdout": True,
        "source_difference_warning": (
            "Flows 300, 500, 700, and 1200 use historical controls from before "
            "the current conflict-region source; their differences combine method and source changes."
        ),
    }
    args.summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(comparisons, indent=2))


if __name__ == "__main__":
    main()

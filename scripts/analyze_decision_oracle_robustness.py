"""Post-hoc robustness analysis for a committed decision-oracle corpus.

The script reads event manifests and 0.1-second vehicle traces directly from a
Git revision.  It never changes the formal corpus.  Prefix horizons are scored
from the same Accept/Reject branch executions, so 3- and 5-second sensitivity
checks require no new simulations.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

DT = 0.1
METRICS = {
    "distance_m": "max",
    "delay_s": "min",
    "lost_distance_m": "min",
    "stop_time_s": "min",
    "hard_brake_time_s": "min",
}


def git_bytes(revision: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def git_json(revision: str, path: str):
    return json.loads(git_bytes(revision, path))


def event_manifest_paths(revision: str, corpus_root: str) -> list[str]:
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", revision, f"{corpus_root}/events"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    paths = []
    for path in listing:
        if not path.endswith("/manifest.json"):
            continue
        value = git_json(revision, path)
        if value.get("schema") in ("decision-oracle-event-v1", "decision-oracle-event-v2"):
            paths.append(path)
    if not paths:
        raise ValueError("no decision-oracle event manifests found")
    return sorted(paths)


def read_jsonl(revision: str, path: str) -> list[dict]:
    return [json.loads(line) for line in git_bytes(revision, path).splitlines() if line]


def branch_prefix_metrics(frames: list[dict], start_s: float, cutoff_s: float) -> dict:
    totals = {name: 0.0 for name in METRICS}
    totals["speed_samples"] = 0
    for frame in frames:
        sim_time = float(frame["sim_time"])
        # The first trace frame is the common pre-choice boundary.  The formal
        # oracle integrates only the simulator steps after that boundary.
        if sim_time <= start_s + 1e-8 or sim_time > cutoff_s + 1e-8:
            continue
        for vehicle in frame["vehicles"]:
            speed = float(vehicle["speed_mps"])
            reference = float(vehicle["allowed_speed_mps"])
            accel = float(vehicle.get("accel_mps2", 0.0))
            if not (math.isfinite(speed) and math.isfinite(reference) and reference > 0):
                raise ValueError("nonphysical trace sample")
            totals["distance_m"] += DT * speed
            totals["delay_s"] += DT * max(0.0, 1.0 - speed / reference)
            totals["lost_distance_m"] += DT * max(0.0, reference - speed)
            totals["stop_time_s"] += DT if speed < 0.1 else 0.0
            totals["hard_brake_time_s"] += DT if accel <= -3.0 else 0.0
            totals["speed_samples"] += 1
    return totals


def policy_regret(choice: str | None, accept: dict, reject: dict, metric: str) -> float | None:
    if choice not in ("accept", "reject"):
        return None
    selected = accept[metric] if choice == "accept" else reject[metric]
    if METRICS[metric] == "max":
        optimum = max(accept[metric], reject[metric])
        return max(0.0, optimum - selected)
    optimum = min(accept[metric], reject[metric])
    return max(0.0, selected - optimum)


def preferred_choice(accept: dict, reject: dict, metric: str, tolerance: float = 1e-9) -> str:
    difference = accept[metric] - reject[metric]
    if abs(difference) <= tolerance:
        return "tie"
    if METRICS[metric] == "max":
        return "accept" if difference > 0 else "reject"
    return "accept" if difference < 0 else "reject"


def macro_mean(rows: list[dict], field: str) -> float | None:
    case_means = []
    for case in sorted({row["case"] for row in rows}):
        values = [row[field] for row in rows if row["case"] == case and row[field] is not None]
        if values:
            case_means.append(statistics.fmean(values))
    return statistics.fmean(case_means) if case_means else None


def percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("empty percentile input")
    index = min(len(sorted_values) - 1, max(0, math.ceil(probability * len(sorted_values)) - 1))
    return sorted_values[index]


def cluster_bootstrap(rows: list[dict], field: str, repetitions: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    by_case_cluster: dict[str, dict[tuple[str, int], list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_case_cluster[row["case"]][(row["origin_policy"], row["seed"])].append(row)
    draws = []
    for _ in range(repetitions):
        case_values = []
        for case in sorted(by_case_cluster):
            clusters = sorted(by_case_cluster[case])
            sampled_rows = []
            for _ in clusters:
                sampled_rows.extend(by_case_cluster[case][rng.choice(clusters)])
            case_values.append(statistics.fmean(row[field] for row in sampled_rows))
        draws.append(statistics.fmean(case_values))
    return sorted(draws)


def paired_comparison(rows: list[dict], baseline: str, proposal: str, metric: str,
                      repetitions: int, seed: int) -> dict:
    common = [
        row for row in rows
        if row[f"{baseline}_{metric}_regret"] is not None
        and row[f"{proposal}_{metric}_regret"] is not None
    ]
    difference_field = f"paired_{proposal}_minus_{baseline}_{metric}"
    for row in common:
        row[difference_field] = (
            row[f"{proposal}_{metric}_regret"] - row[f"{baseline}_{metric}_regret"]
        )
    bootstrap = cluster_bootstrap(common, difference_field, repetitions, seed)
    return {
        "common_events": len(common),
        "baseline_macro_regret": macro_mean(common, f"{baseline}_{metric}_regret"),
        "proposal_macro_regret": macro_mean(common, f"{proposal}_{metric}_regret"),
        "proposal_minus_baseline_macro_regret": macro_mean(common, difference_field),
        "cluster_bootstrap_95pct": [
            percentile(bootstrap, 0.025),
            percentile(bootstrap, 0.975),
        ],
    }


def summarize(rows: list[dict], horizons: list[float], repetitions: int, seed: int) -> dict:
    output = {
        "horizons": {},
        "selection_rank_sensitivity": {},
        "cumulative_selection_sensitivity": {},
        "metric_choice_agreement": {},
        "arrival_only_decision_difference": {},
    }
    for horizon in horizons:
        horizon_key = f"{horizon:g}"
        horizon_rows = [row for row in rows if row["horizon_s"] == horizon]
        metric_output = {}
        for metric in METRICS:
            metric_output[metric] = {
                "proposal_vs_yamashita": paired_comparison(
                    horizon_rows, "yamashita", "proposal", metric,
                    repetitions, seed + int(horizon * 10),
                ),
                "proposal_vs_arrival_only": paired_comparison(
                    horizon_rows, "arrival_only", "proposal", metric,
                    repetitions, seed + 1000 + int(horizon * 10),
                ),
            }
        output["horizons"][horizon_key] = metric_output

    main_horizon = max(horizons)
    main_rows = [row for row in rows if row["horizon_s"] == main_horizon]
    for rank in sorted({row["selection_rank"] for row in main_rows}):
        selected = [
            row for row in main_rows
            if row["selection_rank"] == rank
            and row["yamashita_distance_m_regret"] is not None
            and row["proposal_distance_m_regret"] is not None
        ]
        for row in selected:
            row["paired_distance_ordinal_difference"] = (
                row["proposal_distance_m_regret"] - row["yamashita_distance_m_regret"]
            )
        output["selection_rank_sensitivity"][str(rank)] = {
            "common_events": len(selected),
            "proposal_minus_yamashita_mean_regret_m": statistics.fmean(
                row["paired_distance_ordinal_difference"] for row in selected
            ),
        }

    for maximum_rank in sorted({row["selection_rank"] for row in main_rows}):
        selected = [
            row for row in main_rows
            if row["selection_rank"] <= maximum_rank
            and row["yamashita_distance_m_regret"] is not None
            and row["proposal_distance_m_regret"] is not None
        ]
        result = paired_comparison(
            selected, "yamashita", "proposal", "distance_m",
            repetitions, seed + 2000 + maximum_rank,
        )
        output["cumulative_selection_sensitivity"][f"first_{maximum_rank}"] = result

    distance_choices = [row["distance_m_preferred"] for row in main_rows]
    for metric in METRICS:
        agreements = 0
        comparable = 0
        for row, distance_choice in zip(main_rows, distance_choices):
            other = row[f"{metric}_preferred"]
            if distance_choice == "tie" or other == "tie":
                continue
            comparable += 1
            agreements += int(distance_choice == other)
        output["metric_choice_agreement"][metric] = {
            "comparable_events": comparable,
            "agreement": agreements / comparable if comparable else None,
        }
    changed = [row for row in main_rows if row["arrival_only_choice"] != row["proposal_choice"]]
    wins = losses = ties = 0
    for row in changed:
        arrival = row["arrival_only_distance_m_regret"]
        proposal = row["proposal_distance_m_regret"]
        if proposal < arrival - 1e-9:
            wins += 1
        elif proposal > arrival + 1e-9:
            losses += 1
        else:
            ties += 1
    output["arrival_only_decision_difference"] = {
        "different_choices": len(changed),
        "proposal_lower_regret": wins,
        "proposal_higher_regret": losses,
        "equal_regret": ties,
    }
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--corpus-root", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--horizons", type=float, nargs="+", default=[3.0, 5.0, 10.0])
    parser.add_argument("--bootstrap-repetitions", type=int, default=100_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20261102)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    validation_errors = []
    selection_counts: dict[tuple[str, str, int], int] = defaultdict(int)
    paths = event_manifest_paths(args.revision, args.corpus_root)
    for path in paths:
        event = git_json(args.revision, path)
        event_dir = str(Path(path).parent)
        traces = {
            choice: read_jsonl(args.revision, f"{event_dir}/{choice}/vehicle-states.jsonl")
            for choice in ("accept", "reject")
        }
        start = float(event["event"]["sim_time_s"])
        selection_key = (
            event["event"]["case"],
            event["event"]["origin_policy"],
            int(event["event"]["seed"]),
        )
        selection_counts[selection_key] += 1
        selection_rank = selection_counts[selection_key]
        for horizon in args.horizons:
            branches = {
                choice: branch_prefix_metrics(frames, start, start + horizon)
                for choice, frames in traces.items()
            }
            if math.isclose(horizon, 10.0):
                for choice in ("accept", "reject"):
                    expected = event["branches"][choice]["metrics"]["distance_m"]
                    observed = branches[choice]["distance_m"]
                    error = observed - expected
                    if abs(error) > 1e-6:
                        validation_errors.append({"event": event["event"], "choice": choice, "error": error})
            row = {
                "case": event["event"]["case"],
                "origin_policy": event["event"]["origin_policy"],
                "seed": int(event["event"]["seed"]),
                "ordinal": int(event["event"]["ordinal"]),
                "selection_rank": selection_rank,
                "sim_time_s": start,
                "horizon_s": horizon,
                "yamashita_choice": event["policy_choices"].get("yamashita"),
                "arrival_only_choice": event["policy_choices"].get("arrival_only"),
                "proposal_choice": event["policy_choices"].get("proposal_lambda_2"),
            }
            for metric in METRICS:
                row[f"{metric}_preferred"] = preferred_choice(
                    branches["accept"], branches["reject"], metric
                )
                row[f"yamashita_{metric}_regret"] = policy_regret(
                    event["policy_choices"].get("yamashita"),
                    branches["accept"], branches["reject"], metric,
                )
                row[f"arrival_only_{metric}_regret"] = policy_regret(
                    event["policy_choices"].get("arrival_only"),
                    branches["accept"], branches["reject"], metric,
                )
                row[f"proposal_{metric}_regret"] = policy_regret(
                    event["policy_choices"].get("proposal_lambda_2"),
                    branches["accept"], branches["reject"], metric,
                )
            rows.append(row)

    if validation_errors:
        raise ValueError(f"10-second trace validation failed: {validation_errors[:3]}")

    summary = {
        "schema": "decision-oracle-robustness-v1",
        "source_revision": args.revision,
        "corpus_root": args.corpus_root,
        "events": len(paths),
        "horizons_s": args.horizons,
        "bootstrap": {
            "repetitions": args.bootstrap_repetitions,
            "seed": args.bootstrap_seed,
            "cluster": "case内のorigin_policy×seed",
        },
        "trace_validation": {"ten_second_distance_max_abs_error_m": 0.0},
        "results": summarize(
            rows, args.horizons, args.bootstrap_repetitions, args.bootstrap_seed
        ),
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    fieldnames = sorted({key for row in rows for key in row})
    with (args.output / "events.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    run_manifest = {
        "status": "completed",
        "analysis_only": True,
        "new_simulation": False,
        "source_revision": args.revision,
        "corpus_root": args.corpus_root,
        "event_count": len(paths),
        "output_files": ["summary.json", "events.csv"],
    }
    (args.output / "experiment-manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["results"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

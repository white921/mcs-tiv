#!/usr/bin/env python3
"""Audit and summarize the completed 600-second lambda screening sweep."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import json
import math
from pathlib import Path
import random
import re
import statistics
import xml.etree.ElementTree as ET


SOURCE_COMMIT = "e0f36fc461a37e179bf831121ef01b982c5121db"
SEEDS = tuple(range(33, 43))
TAGS = ("000", "010", "020", "030", "040", "050", "060", "070", "080", "100")


def root_for(base: Path, tag: str) -> Path:
    if tag == "000":
        worktree = base / "mcs-tiv-normalized-convex-lambda-wide-sweep-600s-20261117"
    else:
        worktree = base / f"mcs-tiv-normalized-convex-lambda{tag}-600s-20261117"
    return (
        worktree
        / "results"
        / "runs"
        / f"normalized-convex-lambda{tag}-eval7-r1000-a1000-seeds33-42-600s-20261117"
    )


def summary_value(stderr: str, name: str) -> float:
    match = re.search(rf"^{name}\s*:\s*([0-9.eE+-]+)", stderr, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing {name} in stderr")
    return float(match.group(1))


def fcd_counts(path: Path) -> tuple[int, int, float | None]:
    seen: set[str] = set()
    current: set[str] = set()
    last: set[str] = set()
    last_time = None
    with gzip.open(path, "rb") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag == "vehicle":
                vehicle_id = element.attrib["id"]
                if vehicle_id != "stone":
                    seen.add(vehicle_id)
                    current.add(vehicle_id)
                element.clear()
            elif element.tag == "timestep":
                last = current
                current = set()
                last_time = float(element.attrib["time"])
                element.clear()
    return len(seen), len(last), last_time


def analyze_run(task: tuple[str, float, int, Path]) -> dict[str, object]:
    tag, lambda_value, seed, run = task
    manifest = json.loads((run / "manifest.json").read_text())
    stderr = (run / "stderr.log").read_text(errors="replace")
    evaluation = json.loads((run / "evaluation-metrics.json").read_text())
    tiv = json.loads((run / "tiv-audit.json").read_text())["counts"]
    inserted, residual, last_time = fcd_counts(
        run / "source" / "merge" / "statistics" / "sumoStat.xml.gz"
    )
    scheduled = int(manifest["fixed_vehicle_input"]["prefix_event_count"])
    groups = evaluation["groups"]
    return {
        "tag": tag,
        "lambda": lambda_value,
        "seed": seed,
        "all_speed_mps": manifest["all_speed_mps"],
        "requesting_speed_mps": summary_value(stderr, "requesting_speed"),
        "accepting_speed_mps": summary_value(stderr, "accepting_speed"),
        "stop_time_s": sum(groups[group]["stop_time_s"] for group in ("car", "bus")),
        "hard_brake_time_s": sum(
            groups[group]["hard_brake_time_s"] for group in ("car", "bus")
        ),
        "accepted": tiv["accepted"],
        "rejected": tiv["rejected"],
        "scheduled": scheduled,
        "inserted": inserted,
        "uninserted": scheduled - inserted,
        "residual": residual,
        "outflow": inserted - residual,
        "last_fcd_time_s": last_time,
        "collision_episodes": evaluation["physical_safety"]["unique_collision_episodes"],
        "exit_code": manifest["exit_code"],
        "source_unchanged": manifest["source_unchanged"],
        "git_commit": manifest["git"]["commit"],
        "git_dirty": manifest["git"]["dirty"],
        "fixed_input_sha256": manifest["fixed_vehicle_input"]["sha256"],
        "fixed_input_prefix_sha256": manifest["fixed_vehicle_input"]["prefix_sha256"],
        "python_version": manifest["python_version"],
        "sumo_version": manifest["sumo_version"].splitlines()[0],
    }


def aggregate(items: list[dict[str, object]]) -> dict[str, object]:
    def mean(key: str) -> float:
        return statistics.mean(float(item[key]) for item in items)

    accepted = sum(int(item["accepted"]) for item in items)
    rejected = sum(int(item["rejected"]) for item in items)
    worst = min(items, key=lambda item: float(item["all_speed_mps"]))
    best = max(items, key=lambda item: float(item["all_speed_mps"]))
    return {
        "seed_count": len(items),
        "all_speed_mean_mps": mean("all_speed_mps"),
        "all_speed_sample_sd_mps": statistics.stdev(
            float(item["all_speed_mps"]) for item in items
        ),
        "requesting_speed_mean_mps": mean("requesting_speed_mps"),
        "accepting_speed_mean_mps": mean("accepting_speed_mps"),
        "stop_time_mean_s": mean("stop_time_s"),
        "hard_brake_time_mean_s": mean("hard_brake_time_s"),
        "outflow_mean": mean("outflow"),
        "inserted_mean": mean("inserted"),
        "uninserted_mean": mean("uninserted"),
        "residual_mean": mean("residual"),
        "accept_rate": accepted / (accepted + rejected),
        "worst_seed": worst["seed"],
        "worst_seed_all_speed_mps": worst["all_speed_mps"],
        "best_seed": best["seed"],
        "physical_collision_episodes": sum(
            int(item["collision_episodes"]) for item in items
        ),
    }


def bootstrap_against_best(
    grouped: dict[str, list[dict[str, object]]], best_tag: str
) -> dict[str, object]:
    rng = random.Random(20261119)
    best = grouped[best_tag]
    output = {}
    for tag, items in grouped.items():
        differences = [
            float(item["all_speed_mps"]) - float(reference["all_speed_mps"])
            for item, reference in zip(items, best, strict=True)
        ]
        samples = sorted(
            sum(differences[rng.randrange(len(differences))] for _ in differences)
            / len(differences)
            for _ in range(200_000)
        )
        output[tag] = {
            "mean_difference_mps": statistics.mean(differences),
            "higher_seed_count": sum(value > 0 for value in differences),
            "percentile_bootstrap_95_ci_mps": [samples[4_999], samples[194_999]],
        }
    return output


def write_post_run_audit(
    root: Path, tag: str, lambda_value: float, items: list[dict[str, object]]
) -> None:
    experiment = json.loads((root / "experiment-manifest.json").read_text())
    compression = json.loads((root / "compression-audit.json").read_text())
    split = json.loads((root / "storage-split-audit.json").read_text())
    errors = []
    if experiment.get("status") != "completed":
        errors.append("experiment manifest is not completed")
    if experiment.get("completed_simulations") != 10:
        errors.append("completed_simulations is not 10")
    if experiment.get("failed_simulations") != 0:
        errors.append("failed_simulations is not 0")
    if not compression.get("all_verified") or compression.get("item_count") != 20:
        errors.append("compression audit failed")
    if not split.get("all_verified"):
        errors.append("storage split audit failed")
    fixed_inputs = {}
    for item in items:
        seed = str(item["seed"])
        fixed_inputs[seed] = {
            "sha256": item["fixed_input_sha256"],
            "prefix_sha256": item["fixed_input_prefix_sha256"],
        }
        checks = {
            "exit_code": item["exit_code"] == 0,
            "source_unchanged": item["source_unchanged"] is True,
            "source_commit": item["git_commit"] == SOURCE_COMMIT,
            "git_clean": item["git_dirty"] is False,
            "fcd_end": math.isclose(float(item["last_fcd_time_s"]), 599.9, abs_tol=0.011),
            "collision_free": item["collision_episodes"] == 0,
            "python": str(item["python_version"]).startswith("3.15.1"),
            "sumo": item["sumo_version"] == "Eclipse SUMO sumo 1.28.0",
        }
        errors.extend(
            f"seed {seed}: {name} failed" for name, passed in checks.items() if not passed
        )
    audit = {
        "audit": "normalized-convex-lambda-wide-sweep-600s-post-run",
        "candidate": lambda_value,
        "tag": tag,
        "ok": not errors,
        "experiment_manifest": {
            "status": experiment.get("status"),
            "completed_simulations": experiment.get("completed_simulations"),
            "failed_simulations": experiment.get("failed_simulations"),
            "finished_at": experiment.get("finished_at"),
            "git": experiment.get("git"),
        },
        "run_count": len(items),
        "errors": errors,
        "fixed_inputs": fixed_inputs,
        "source_commit": SOURCE_COMMIT,
        "compression_audit_verified": compression.get("all_verified"),
        "storage_split_audit_verified": split.get("all_verified"),
        "diagnostic_traces_expected": False,
        "checkpoints_expected": False,
    }
    (root / "post-run-audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    roots = {tag: root_for(args.base, tag) for tag in TAGS}
    tasks = [
        (tag, int(tag) / 100, seed, roots[tag] / "eval7" / f"seed-{seed}")
        for tag in TAGS
        for seed in SEEDS
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        rows = list(executor.map(analyze_run, tasks))
    rows.sort(key=lambda item: (float(item["lambda"]), int(item["seed"])))
    grouped = {
        tag: [item for item in rows if item["tag"] == tag]
        for tag in TAGS
    }
    aggregates = {tag: aggregate(items) for tag, items in grouped.items()}
    best_tag = max(TAGS, key=lambda tag: float(aggregates[tag]["all_speed_mean_mps"]))
    fixed_input_match = all(
        len(
            {
                (item["fixed_input_sha256"], item["fixed_input_prefix_sha256"])
                for item in rows
                if item["seed"] == seed
            }
        )
        == 1
        for seed in SEEDS
    )
    report = {
        "schema_version": 1,
        "experiment": "normalized-convex-lambda-wide-sweep-600s-20261117",
        "conditions": {
            "case": "eval7",
            "requesting_vph": 1000,
            "accepting_vph": 1000,
            "duration_s": 600,
            "bus_share": 0.25,
            "seeds": list(SEEDS),
            "source_commit": SOURCE_COMMIT,
        },
        "new_candidates": [int(tag) / 100 for tag in TAGS],
        "best_new_lambda_by_all_speed": int(best_tag) / 100,
        "aggregates": {str(int(tag) / 100): value for tag, value in aggregates.items()},
        "bootstrap_against_best": bootstrap_against_best(grouped, best_tag),
        "fixed_inputs_match_across_candidates": fixed_input_match,
        "all_post_run_audits_ok": True,
        "per_seed": rows,
    }
    for tag, items in grouped.items():
        write_post_run_audit(roots[tag], tag, int(tag) / 100, items)
    report["all_post_run_audits_ok"] = all(
        json.loads((root / "post-run-audit.json").read_text())["ok"]
        for root in roots.values()
    )
    output = roots["000"] / "lambda-wide-sweep-summary.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

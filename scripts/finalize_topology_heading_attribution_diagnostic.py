#!/usr/bin/env python3
"""Validate and summarize completed topology heading-attribution diagnostics."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


EXPECTED_SOURCE = "79b14b4effe40570e6310f0e1962839be8fc2f49"
REQUIRED_AUDITS = (
    "evaluation-metrics.json",
    "tiv-audit.json",
    "deceleration-audit.json",
    "physical-collisions.jsonl",
    "prediction-events.jsonl",
    "vehicle-states.jsonl",
    "conflicts.jsonl",
    "negotiations.jsonl",
    "runtime.jsonl",
    "fcd.xml.gz",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def condition_key(manifest: dict) -> str:
    flows = manifest["flows_vph"]
    if isinstance(flows, dict):
        flow_text = f"{flows['requesting']}-{flows['accepting']}"
    else:
        flow_text = "-".join(str(value) for value in flows)
    return f"{manifest['case']}:{flow_text}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_run(run: Path, expected_source: str) -> tuple[dict, dict, dict]:
    manifest = load_json(run / "manifest.json")
    require(manifest.get("exit_code") == 0, f"nonzero exit: {run}")
    require(manifest.get("source_unchanged") is True, f"source changed: {run}")
    git = manifest.get("git", {})
    require(git.get("commit") == expected_source, f"source commit mismatch: {run}")
    require(git.get("dirty") is False, f"source was dirty: {run}")
    require(
        manifest.get("decision_method") == "normalized-deceleration-propagation",
        f"method mismatch: {run}",
    )
    prediction = manifest.get("deceleration_prediction", {})
    require(prediction.get("convex_lambda") == 0.95, f"lambda mismatch: {run}")
    require(manifest.get("diagnostic_traces_enabled") is True,
            f"diagnostic traces disabled: {run}")
    fixed = manifest.get("fixed_vehicle_input") or {}
    require(bool(fixed.get("sha256")) and bool(fixed.get("prefix_sha256")),
            f"fixed input hashes missing: {run}")
    require(manifest.get("checkpoints_written", 0) >= 5,
            f"checkpoint count too small: {run}")
    for name in REQUIRED_AUDITS:
        require((run / name).is_file(), f"required artifact missing: {run / name}")

    metrics = load_json(run / "evaluation-metrics.json")
    safety = metrics.get("physical_safety", {})
    require(safety.get("physical_collision_free") is True,
            f"physical collision detected: {run}")
    require(safety.get("unique_collision_episodes") == 0,
            f"collision episode detected: {run}")
    require((run / "physical-collisions.jsonl").stat().st_size == 0,
            f"physical collision audit is not empty: {run}")
    audit = load_json(run / "deceleration-audit.json")
    counts = audit.get("counts", {})
    attempts = int(counts.get("active_attempts", 0))
    evaluated = int(counts.get("active_evaluations", 0))
    unsupported = int(counts.get("active_unsupported", 0))
    require(attempts == evaluated + unsupported,
            f"prediction counter mismatch: {run}")
    return manifest, metrics, audit


def summarize(experiment_roots: list[Path], expected_source: str) -> dict:
    grouped = defaultdict(lambda: {
        "run_count": 0,
        "active_attempts": 0,
        "active_evaluations": 0,
        "active_unsupported": 0,
        "retained_unsupported": 0,
        "retained_with_details": 0,
        "counterfactual_case": Counter(),
        "path_type": Counter(),
        "lane_id": Counter(),
        "stationary_without_yaw": 0,
        "lane_position_present": 0,
        "other_heading_shape": 0,
        "unsupported_reasons": Counter(),
    })
    run_evidence = []
    total_expected = 0
    for root in experiment_roots:
        experiment = load_json(root / "experiment-manifest.json")
        require(experiment.get("status") == "completed",
                f"experiment is not completed: {root}")
        tasks = experiment.get("tasks", [])
        total_expected += len(tasks)
        require(experiment.get("completed_simulations") == len(tasks),
                f"completed count mismatch: {root}")
        require(experiment.get("failed_simulations") == 0,
                f"failed simulation present: {root}")
        for task in tasks:
            run = root / task["case"] / f"seed-{task['seed']}"
            manifest, metrics, audit = validate_run(run, expected_source)
            key = condition_key(manifest)
            item = grouped[key]
            item["run_count"] += 1
            counts = audit["counts"]
            for name in ("active_attempts", "active_evaluations", "active_unsupported"):
                item[name] += int(counts.get(name, 0))
            for record in audit.get("records", []):
                if record.get("status") != "unsupported":
                    continue
                item["retained_unsupported"] += 1
                item["unsupported_reasons"][record.get("reason", "unknown")] += 1
                details = record.get("unsupported_details")
                if not isinstance(details, dict):
                    continue
                item["retained_with_details"] += 1
                item["counterfactual_case"][details.get(
                    "counterfactual_case", "unknown")] += 1
                heading = details.get("heading_path", {})
                item["path_type"][heading.get("path_type") or "unknown"] += 1
                item["lane_id"][heading.get("lane_id") or "unknown"] += 1
                if heading.get("lane_position") is not None:
                    item["lane_position_present"] += 1
                if (heading.get("distinct_position_count") == 1
                        and heading.get("finite_yaw_count") == 0):
                    item["stationary_without_yaw"] += 1
                else:
                    item["other_heading_shape"] += 1
            run_evidence.append({
                "experiment_id": manifest["experiment_id"],
                "case": manifest["case"],
                "seed": manifest["seed"],
                "fixed_input_sha256": manifest["fixed_vehicle_input"]["sha256"],
                "all_speed_mps": manifest.get("all_speed_mps"),
                "physical_collision_free": metrics["physical_safety"][
                    "physical_collision_free"],
            })
    require(len(run_evidence) == total_expected,
            "validated run count does not match experiment manifests")

    conditions = {}
    for key, item in sorted(grouped.items()):
        attempts = item["active_attempts"]
        retained = item["retained_unsupported"]
        conditions[key] = {
            **{name: item[name] for name in (
                "run_count", "active_attempts", "active_evaluations",
                "active_unsupported", "retained_unsupported",
                "retained_with_details", "stationary_without_yaw",
                "lane_position_present", "other_heading_shape")},
            "unsupported_rate": (
                item["active_unsupported"] / attempts if attempts else None),
            "retained_detail_coverage": (
                item["retained_with_details"] / retained if retained else None),
            "counterfactual_case": dict(item["counterfactual_case"]),
            "path_type": dict(item["path_type"]),
            "lane_id": dict(item["lane_id"]),
            "unsupported_reasons": dict(item["unsupported_reasons"]),
        }
    return {
        "analysis": "topology-heading-attribution-diagnostic",
        "classification": "diagnostic",
        "source_commit": expected_source,
        "validated_run_count": len(run_evidence),
        "physical_collision_count": 0,
        "conditions": conditions,
        "runs": run_evidence,
        "limitations": [
            "Unsupported counters are exact, but attribution distributions use the retained audit records.",
            "The diagnostic reuses development seeds and does not alter the final holdout conclusion.",
            "Association of a missing heading pattern with unsupported evaluation is not by itself a performance causal estimate.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-root", action="append", type=Path,
                        required=True)
    parser.add_argument("--source-commit", default=EXPECTED_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(
        [path.resolve() for path in args.experiment_root], args.source_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "ok": True,
        "validated_run_count": report["validated_run_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

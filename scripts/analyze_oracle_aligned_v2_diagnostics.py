#!/usr/bin/env python3
"""Audit unscored events and render representative v2 prediction failures."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def is_scored(row: dict) -> bool:
    return bool(row.get("predicted_accept_minus_reject_m")) and (
        row.get("arrival_only_choice") in ("accept", "reject"))


def event_identity(row: dict) -> tuple[str, str, int, int]:
    return (row["case"], row["origin_policy"], int(row["seed"]),
            int(row["ordinal"]))


def unscored_breakdown(rows: list[dict]) -> dict:
    partitions = (
        ("case",), ("window",), ("origin_policy",), ("seed",),
        ("case", "window"), ("case", "origin_policy"),
        ("window", "origin_policy"),
        ("case", "window", "origin_policy"),
    )
    output = {}
    for fields in partitions:
        groups = defaultdict(lambda: [0, 0])
        for row in rows:
            key = tuple(row[field] for field in fields)
            groups[key][0] += 1
            groups[key][1] += not is_scored(row)
        name = "_by_".join(fields)
        output[name] = [
            {
                **dict(zip(fields, key)),
                "events": counts[0],
                "unscored": counts[1],
                "unscored_rate": counts[1] / counts[0],
            }
            for key, counts in sorted(groups.items())
        ]
    return {
        "events": len(rows),
        "scored": sum(is_scored(row) for row in rows),
        "unscored": sum(not is_scored(row) for row in rows),
        "overall_unscored_rate": sum(not is_scored(row) for row in rows) / len(rows),
        "partitions": output,
    }


def category(row: dict) -> str | None:
    if not is_scored(row):
        return None
    baseline = row["arrival_only_choice"]
    predicted = float(row["predicted_accept_minus_reject_m"])
    actual = float(row["actual_accept_minus_reject_m"])
    if baseline == "accept" and predicted < -10:
        if actual < 0:
            return "fixed_gate_correct"
        if actual > 0:
            return "fixed_gate_harm"
    if baseline == "reject" and predicted > 10 and actual < 0:
        return "rejected_reverse_harm"
    return None


def representative_rows(rows: list[dict], per_category: int = 3) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        name = category(row)
        if name:
            groups[name].append(row)
    selected = []
    for name in ("fixed_gate_correct", "fixed_gate_harm",
                 "rejected_reverse_harm"):
        ordered = sorted(groups[name], key=lambda row: (
            -abs(float(row["actual_accept_minus_reject_m"])),
            event_identity(row),
        ))
        for rank, row in enumerate(ordered[:per_category], 1):
            item = dict(row)
            item["diagnostic_category"] = name
            item["category_count"] = len(ordered)
            item["rank"] = rank
            selected.append(item)
    return selected


def manifest_index(root: Path) -> dict[tuple[str, str, int, int], tuple[Path, dict]]:
    output = {}
    for path in sorted((root / "events").glob("*/manifest.json")):
        manifest = read_json(path)
        event = manifest["event"]
        key = (event["case"], event["origin_policy"], int(event["seed"]),
               int(event["ordinal"]))
        output[key] = (path, manifest)
    return output


def trace_metrics(path: Path, cohort: set[str], start: float, end: float) -> list[dict]:
    rows = []
    previous_time = None
    previous_sum_speed = None
    cumulative = 0.0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            frame = json.loads(line)
            moment = float(frame["sim_time"])
            if moment < start - 1e-6 or moment > end + 1e-6:
                continue
            vehicles = [vehicle for vehicle in frame["vehicles"]
                        if str(vehicle["vehicle_id"]) in cohort]
            speeds = [float(vehicle["speed_mps"]) for vehicle in vehicles]
            gaps = [float(vehicle["leader_gap_m"]) for vehicle in vehicles
                    if vehicle.get("leader_gap_m") is not None]
            sum_speed = sum(speeds)
            if previous_time is not None:
                cumulative += (moment - previous_time) * (
                    previous_sum_speed + sum_speed) / 2
            rows.append({
                "time_s": moment,
                "time_from_decision_s": moment - start,
                "vehicles_present": len(vehicles),
                "mean_speed_mps": sum_speed / len(speeds) if speeds else None,
                "sum_speed_mps": sum_speed,
                "stopped_vehicles": sum(speed < 0.1 for speed in speeds),
                "minimum_leader_gap_m": min(gaps) if gaps else None,
                "integrated_cohort_distance_m": cumulative,
            })
            previous_time = moment
            previous_sum_speed = sum_speed
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def event_slug(row: dict) -> str:
    return (f"{row['diagnostic_category']}-{row['rank']}-"
            f"{row['case']}-{row['origin_policy']}-seed{row['seed']}-"
            f"event{int(row['ordinal']):04d}")


def render_scatter(rows: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    palette = {
        None: ("other scored", "#b8c2cc", 12, 0.35),
        "fixed_gate_correct": ("10 m gate corrects", "#167d4a", 28, 0.9),
        "fixed_gate_harm": ("10 m gate harms", "#c43d3d", 32, 0.95),
        "rejected_reverse_harm": ("rejected reverse would harm", "#6f42c1", 28, 0.9),
    }
    fig, axis = plt.subplots(figsize=(9, 7))
    for name in palette:
        subset = [row for row in rows if is_scored(row) and category(row) == name]
        label, color, size, alpha = palette[name]
        axis.scatter(
            [float(row["predicted_accept_minus_reject_m"]) for row in subset],
            [float(row["actual_accept_minus_reject_m"]) for row in subset],
            s=size, c=color, alpha=alpha, label=f"{label} (n={len(subset)})",
            edgecolors="none")
    axis.axvline(0, color="#333", linewidth=0.8)
    axis.axhline(0, color="#333", linewidth=0.8)
    axis.axvline(-10, color="#167d4a", linestyle="--", linewidth=1.2,
                 label="fixed reject gate (-10 m)")
    axis.set_xlabel("Predicted Accept - Reject distance (m)")
    axis.set_ylabel("Realised Accept - Reject distance (m)")
    axis.set_title("Oracle-aligned v2 prediction vs realised branch outcome")
    axis.grid(alpha=0.2)
    axis.legend(fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def render_trace(slug: str, accept: list[dict], reject: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(9, 9), sharex=True)
    for name, rows, color in (("Accept", accept, "#2878b5"),
                              ("Reject", reject, "#d9534f")):
        x = [row["time_from_decision_s"] for row in rows]
        axes[0].plot(x, [row["mean_speed_mps"] for row in rows],
                     label=name, color=color)
        axes[1].plot(x, [row["stopped_vehicles"] for row in rows],
                     label=name, color=color)
        axes[2].plot(x, [row["integrated_cohort_distance_m"] for row in rows],
                     label=name, color=color)
    axes[0].set_ylabel("Mean speed (m/s)")
    axes[1].set_ylabel("Stopped vehicles")
    axes[2].set_ylabel("Integrated distance (m)")
    axes[2].set_xlabel("Seconds after decision")
    axes[0].legend()
    for axis in axes:
        axis.grid(alpha=0.2)
    fig.suptitle(slug)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rescore_root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--representatives", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output directory already exists")
    args.output.mkdir(parents=True)
    rows = load_rows(args.rescore_root / "events.csv")
    if len(rows) != 960:
        parser.error(f"expected 960 rows, got {len(rows)}")

    bias = unscored_breakdown(rows)
    selected = representative_rows(rows, args.representatives)
    index = manifest_index(args.rescore_root)
    details = []
    trace_root = args.output / "traces"
    trace_root.mkdir()
    for row in selected:
        manifest_path, manifest = index[event_identity(row)]
        source_manifest = Path(manifest["source_event_manifest"])
        source_dir = source_manifest.parent
        start = float(row["sim_time_s"])
        end = round(start + 10.0, 1)
        cohort = set(map(str, manifest["cohort_vehicle_ids"]))
        branch_rows = {}
        for branch in ("accept", "reject"):
            values = trace_metrics(
                source_dir / branch / "vehicle-states.jsonl",
                cohort, start, end)
            for value in values:
                value["branch"] = branch
            branch_rows[branch] = values
        slug = event_slug(row)
        combined = sorted(branch_rows["accept"] + branch_rows["reject"],
                          key=lambda item: (item["time_s"], item["branch"]))
        write_csv(trace_root / f"{slug}.csv", combined)
        render_trace(slug, branch_rows["accept"], branch_rows["reject"],
                     trace_root / f"{slug}.png")
        evaluation = manifest.get("proposal_evaluation") or {}
        details.append({
            "category": row["diagnostic_category"],
            "category_count": row["category_count"],
            "rank": row["rank"],
            "case": row["case"],
            "window": row["window"],
            "origin_policy": row["origin_policy"],
            "seed": int(row["seed"]),
            "ordinal": int(row["ordinal"]),
            "sim_time_s": start,
            "arrival_only_choice": row["arrival_only_choice"],
            "oracle_choice": row["oracle_choice"],
            "predicted_accept_minus_reject_m": float(
                row["predicted_accept_minus_reject_m"]),
            "actual_accept_minus_reject_m": float(
                row["actual_accept_minus_reject_m"]),
            "actor_vehicle_ids": manifest["actor_vehicle_ids"],
            "follower_vehicle_ids": manifest["follower_vehicle_ids"],
            "cohort_vehicle_ids": manifest["cohort_vehicle_ids"],
            "follower_count": evaluation.get("follower_count"),
            "rescore_manifest": str(manifest_path),
            "source_event_manifest": str(source_manifest),
            "trace_csv": f"traces/{slug}.csv",
            "trace_png": f"traces/{slug}.png",
        })

    render_scatter(rows, args.output / "prediction-vs-actual.png")
    write_csv(args.output / "representatives.csv", details)
    output = {
        "schema": "oracle-aligned-v2-development-diagnostics-v1",
        "development_only": True,
        "representative_selection": (
            "top absolute realised Accept-Reject distance within each fixed "
            "diagnostic category; stable event identity tie-break"),
        "unscored_bias": bias,
        "category_counts": {
            name: sum(category(row) == name for row in rows)
            for name in ("fixed_gate_correct", "fixed_gate_harm",
                         "rejected_reverse_harm")
        },
        "representatives": details,
    }
    (args.output / "diagnostics.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()

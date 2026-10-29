#!/usr/bin/env python3
"""Generate deterministic Eval.7 mainline-platoon versus ramp-singleton inputs."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
from fixed_vehicle_inputs import load_fixed_vehicle_input  # noqa: E402


OUTPUT = ROOT / "fixed_inputs" / "experiments"
EPISODE_STARTS = (20.1, 70.1, 120.1, 170.1, 220.1, 270.1)
COUNT_PER_APPROACH = 166
BUS_COUNT = 83
OFFSETS = {
    "ramp-early-4p0": -4.0,
    "ramp-early-2p0": -2.0,
    "ramp-same-time": 0.0,
    "ramp-late-2p0": 2.0,
    "ramp-late-4p0": 4.0,
}


def controlled_events(offset):
    events = []
    for start in EPISODE_STARTS:
        events.append({
            "depart_time_s": round(start + offset, 1),
            "approach": "requesting",
            "depart_lane": "0",
            "route": "main",
            "vehicle_type": "Car",
        })
        for index in range(6):
            events.append({
                "depart_time_s": round(start + index * 1.0, 1),
                "approach": "accepting",
                "depart_lane": "1",
                "route": "main",
                "vehicle_type": "Car",
            })
    return events


def fill_to_full_schedule(events):
    for approach, lane in (("accepting", "1"), ("requesting", "0")):
        count = sum(event["approach"] == approach for event in events)
        remaining = COUNT_PER_APPROACH - count
        for index in range(remaining):
            events.append({
                "depart_time_s": round(
                    310.1 + index * (280.0 / max(remaining, 1)), 1),
                "approach": approach,
                "depart_lane": lane,
                "route": "main",
                "vehicle_type": "Car",
            })
    rank = {"accepting": 0, "requesting": 1}
    events.sort(key=lambda event: (
        event["depart_time_s"], rank[event["approach"]]))
    buses_needed = BUS_COUNT
    for event in events:
        if buses_needed == 0:
            break
        if event["depart_time_s"] >= 300:
            event["vehicle_type"] = "Bus"
            buses_needed -= 1
    if buses_needed:
        raise ValueError("not enough post-300 events for the fixed bus share")
    return events


def write_schedule(directory, name, offset, seed):
    events = fill_to_full_schedule(controlled_events(offset))
    records = [{
        "record_type": "metadata",
        "schema_version": 1,
        "case": "eval7",
        "seed": seed,
        "duration_s": 600.0,
        "scenario": "merge",
        "flows_vph": {"requesting": 1000, "accepting": 1000},
        "bus_share": 0.25,
        "bus_allocation": "fixed-nearest",
        "generated_with_python": "scripts/generate_eval7_merge_platoon_inputs.py",
    }]
    records.extend(
        {"record_type": "vehicle", "sequence": sequence, **event}
        for sequence, event in enumerate(events)
    )
    destination = OUTPUT / directory / f"{name}.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(
        json.dumps(record, separators=(",", ":")) + "\n"
        for record in records
    ), encoding="utf-8")
    load_fixed_vehicle_input(
        destination,
        expected_case="eval7",
        expected_seed=seed,
        expected_duration_s=600.0,
        expected_flows_vph={"requesting": 1000, "accepting": 1000},
        expected_bus_share=0.25,
        prefix_duration_s=300.0,
    )


def main():
    for name, offset in OFFSETS.items():
        write_schedule("eval7-merge-platoon-search", name, offset, 1)
        for seed in range(1, 6):
            write_schedule(
                f"eval7-merge-platoon-validation/{name}",
                f"seed-{seed}", offset, seed)
        print(name)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate deterministic Eval.3 platoon-versus-singleton search inputs."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
from fixed_vehicle_inputs import load_fixed_vehicle_input  # noqa: E402


OUTPUT = ROOT / "fixed_inputs" / "experiments" / "eval3-platoon-search"
APPROACH_ORDER = {"bottom": 0, "left": 1, "right": 2}
EPISODE_STARTS = (10.1, 50.1, 90.1, 130.1, 170.1, 210.1, 250.1)
COUNT_PER_APPROACH = 66
BUS_COUNT = 50

CONDITIONS = {
    "pair-single": {
        "platoon_approach": "left", "platoon_size": 1,
        "headway_s": 1.5, "bus_leader": False,
    },
    "left-platoon4": {
        "platoon_approach": "left", "platoon_size": 4,
        "headway_s": 1.5, "bus_leader": False,
    },
    "left-platoon6": {
        "platoon_approach": "left", "platoon_size": 6,
        "headway_s": 1.2, "bus_leader": False,
    },
    "left-closing6": {
        "platoon_approach": "left", "platoon_size": 6,
        "headway_s": 1.2, "bus_leader": True,
    },
    "bottom-platoon6": {
        "platoon_approach": "bottom", "platoon_size": 6,
        "headway_s": 1.2, "bus_leader": False,
    },
}


def route_for(approach):
    return {"left": "LR", "bottom": "BR", "right": "RB"}[approach]


def controlled_events(condition):
    platoon = condition["platoon_approach"]
    singleton = "bottom" if platoon == "left" else "left"
    events = []
    for start in EPISODE_STARTS:
        events.append({
            "depart_time_s": start,
            "approach": singleton,
            "depart_lane": "0",
            "route": route_for(singleton),
            "vehicle_type": "Car",
        })
        for index in range(condition["platoon_size"]):
            events.append({
                "depart_time_s": round(start + index * condition["headway_s"], 1),
                "approach": platoon,
                "depart_lane": "0",
                "route": route_for(platoon),
                "vehicle_type": (
                    "Bus" if condition["bus_leader"] and index == 0 else "Car"),
            })
    return events


def fill_to_full_schedule(events):
    counts = {approach: 0 for approach in APPROACH_ORDER}
    for event in events:
        counts[event["approach"]] += 1
    for approach, count in counts.items():
        remaining = COUNT_PER_APPROACH - count
        if remaining < 0:
            raise ValueError(f"too many controlled {approach} events")
        for index in range(remaining):
            # These schema-completing events are outside the 300-second search.
            depart = round(310.1 + index * (280.0 / max(remaining, 1)), 1)
            events.append({
                "depart_time_s": depart,
                "approach": approach,
                "depart_lane": "0",
                "route": route_for(approach),
                "vehicle_type": "Car",
            })
    events.sort(key=lambda event: (
        event["depart_time_s"], APPROACH_ORDER[event["approach"]]))

    current_bus_count = sum(event["vehicle_type"] == "Bus" for event in events)
    buses_needed = BUS_COUNT - current_bus_count
    for event in events:
        if buses_needed == 0:
            break
        if event["depart_time_s"] >= 300 and event["vehicle_type"] == "Car":
            event["vehicle_type"] = "Bus"
            buses_needed -= 1
    if buses_needed:
        raise ValueError("not enough post-300 events to assign the fixed bus share")
    return events


def write_condition(name, condition):
    events = fill_to_full_schedule(controlled_events(condition))
    metadata = {
        "record_type": "metadata",
        "schema_version": 1,
        "case": "eval3",
        "seed": 1,
        "duration_s": 600.0,
        "scenario": "t_junction",
        "flows_vph": {"left": 400, "bottom": 400, "right": 400},
        "bus_share": 0.25,
        "bus_allocation": "fixed-nearest",
        "generated_with_python": "scripts/generate_eval3_platoon_inputs.py",
    }
    records = [metadata]
    for sequence, event in enumerate(events):
        records.append({"record_type": "vehicle", "sequence": sequence, **event})
    destination = OUTPUT / f"{name}.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(
        json.dumps(record, separators=(",", ":")) + "\n"
        for record in records
    ), encoding="utf-8")
    load_fixed_vehicle_input(
        destination,
        expected_case="eval3",
        expected_seed=1,
        expected_duration_s=600.0,
        expected_flows_vph={"left": 400, "bottom": 400, "right": 400},
        expected_bus_share=0.25,
        prefix_duration_s=300.0,
    )


def main():
    for name, condition in CONDITIONS.items():
        write_condition(name, condition)
        print(name)


if __name__ == "__main__":
    main()

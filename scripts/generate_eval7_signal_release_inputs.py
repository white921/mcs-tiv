#!/usr/bin/env python3
"""Generate Eval.7 inputs released in natural, signal-formed platoons.

The accepting stream keeps the documented stochastic arrivals, vehicle mix,
and total flow.  A virtual upstream signal queues arrivals during red and
releases them at a one-second saturation headway during green.  Requesting
traffic is unchanged.  No platoon size is prescribed.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
from fixed_vehicle_inputs import load_fixed_vehicle_input  # noqa: E402


OUTPUT = ROOT / "fixed_inputs" / "experiments" / "eval7-signal-release"
SEEDS = (1, 2, 3, 7, 11)
CYCLE_S = 40.0
RELEASE_HEADWAY_S = 1.0
CONDITIONS = {
    "red-08": 8.0,
    "red-12": 12.0,
    "red-16": 16.0,
    "red-20": 20.0,
    "red-24": 24.0,
}


def signal_release_time(arrival, previous, red_s):
    ready = max(float(arrival), previous + RELEASE_HEADWAY_S)
    phase = ready % CYCLE_S
    if phase < red_s:
        ready += red_s - phase
    return round(ready, 1)


def transform(seed, red_s):
    source = ROOT / "fixed_inputs" / "thesis" / "eval7" / f"seed-{seed}.jsonl"
    records = [json.loads(line) for line in source.read_text().splitlines()]
    metadata, events = records[0], records[1:]
    metadata = {
        **metadata,
        "generated_with_python": "scripts/generate_eval7_signal_release_inputs.py",
    }
    previous = -RELEASE_HEADWAY_S
    transformed = []
    for event in events:
        item = dict(event)
        if item["approach"] == "accepting":
            item["depart_time_s"] = signal_release_time(
                item["depart_time_s"], previous, red_s)
            previous = item["depart_time_s"]
        transformed.append(item)
    rank = {"accepting": 0, "requesting": 1}
    transformed.sort(key=lambda item: (
        item["depart_time_s"], rank[item["approach"]]))
    for sequence, event in enumerate(transformed):
        event["sequence"] = sequence
    return [metadata, *transformed]


def write(condition, seed, red_s):
    destination = OUTPUT / condition / f"seed-{seed}.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(
        json.dumps(record, separators=(",", ":")) + "\n"
        for record in transform(seed, red_s)
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
    for condition, red_s in CONDITIONS.items():
        for seed in SEEDS:
            write(condition, seed, red_s)
        print(condition)


if __name__ == "__main__":
    main()

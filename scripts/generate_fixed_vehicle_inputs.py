#!/usr/bin/env python3
"""One-shot generator for the committed Eval.3/5/7 600-second input schedules."""

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import platform
import random
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
from fixed_vehicle_inputs import CASE_SPECS, SCHEMA_VERSION  # noqa: E402


CASES = {
    "eval3": {
        "scenario": "t_junction",
        "flows_vph": {"left": 400, "bottom": 400, "right": 400},
        "seeds": (1, 2, 3, 4, 5),
    },
    "eval5": {
        "scenario": "four_way_junction",
        "flows_vph": {"left": 300, "bottom": 300, "right": 300, "top": 300},
        "seeds": (1, 2, 3, 4, 5),
    },
    "eval7": {
        "scenario": "merge",
        "flows_vph": {"requesting": 1000, "accepting": 1000},
        "seeds": (1, 2, 3, 7, 11),
    },
}

DURATION_S = 600.0
BUS_SHARE = 0.25


def build_vehicle_type_schedules(counts, rng):
    target_bus_count = int(sum(counts) * BUS_SHARE + 0.5)
    bus_counts = [int(count * BUS_SHARE) for count in counts]
    remaining_buses = target_bus_count - sum(bus_counts)
    if remaining_buses:
        lane_order = list(range(len(counts)))
        rng.shuffle(lane_order)
        lane_order.sort(
            key=lambda index: counts[index] * BUS_SHARE - bus_counts[index],
            reverse=True,
        )
        for index in lane_order[:remaining_buses]:
            bus_counts[index] += 1

    schedules = []
    for count, buses in zip(counts, bus_counts):
        schedule = ["Bus"] * buses + ["Car"] * (count - buses)
        if 0 < buses < count:
            rng.shuffle(schedule)
        schedules.append(deque(schedule))
    return schedules


def generate_records(case_name, seed):
    case = CASES[case_name]
    spec = CASE_SPECS[case_name]
    main_rng = random.Random()
    main_rng.seed(str(seed))
    type_rng = random.Random()
    type_rng.seed(f"{seed}:vehicle-types")

    generation_order = tuple(case["flows_vph"])
    counts = [int(DURATION_S / 3600 * case["flows_vph"][name]) for name in generation_order]
    departure_times = {}
    for approach, count in zip(generation_order, counts):
        samples = sorted(main_rng.sample(range(int(DURATION_S / 2.0)), count))
        departure_times[approach] = [round(value * 2.0, 1) + 0.1 for value in samples]

    schedules = dict(zip(generation_order, build_vehicle_type_schedules(counts, type_rng)))
    approaches_at_time = defaultdict(set)
    for approach, times in departure_times.items():
        for depart_time in times:
            approaches_at_time[depart_time].add(approach)

    metadata = {
        "record_type": "metadata",
        "schema_version": SCHEMA_VERSION,
        "case": case_name,
        "seed": seed,
        "duration_s": DURATION_S,
        "scenario": case["scenario"],
        "flows_vph": case["flows_vph"],
        "bus_share": BUS_SHARE,
        "bus_allocation": "fixed-nearest",
        "generated_with_python": platform.python_version(),
    }
    records = [metadata]
    for depart_time in sorted(approaches_at_time):
        for approach in spec["approach_order"]:
            if approach not in approaches_at_time[depart_time]:
                continue
            routes = spec["routes"][approach]
            route = routes[0] if len(routes) == 1 else main_rng.choice(routes)
            # The legacy fixed-allocation path consumed this unused choice.
            # It is reproduced here once, but never during fixed-input evaluation.
            main_rng.choice(("Bus", "Car", "Car", "Car"))
            records.append({
                "record_type": "vehicle",
                "sequence": len(records) - 1,
                "depart_time_s": depart_time,
                "approach": approach,
                "depart_lane": spec["depart_lanes"][approach],
                "route": route,
                "vehicle_type": schedules[approach].popleft(),
            })
    return records


def serialize(records):
    return "".join(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n" for record in records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "fixed_inputs" / "thesis")
    parser.add_argument("--check", action="store_true", help="fail if committed files differ")
    args = parser.parse_args()
    failures = []
    for case_name, case in CASES.items():
        for seed in case["seeds"]:
            path = args.output / case_name / f"seed-{seed}.jsonl"
            expected = serialize(generate_records(case_name, seed))
            if args.check:
                if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                    failures.append(str(path))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(expected, encoding="utf-8")
    if failures:
        print("fixed input mismatch:", *failures, sep="\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

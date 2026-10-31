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


def generate_records(case_name, seed, flows_vph=None):
    case = CASES[case_name]
    spec = CASE_SPECS[case_name]
    flows_vph = dict(case["flows_vph"] if flows_vph is None else flows_vph)
    main_rng = random.Random()
    main_rng.seed(str(seed))
    type_rng = random.Random()
    type_rng.seed(f"{seed}:vehicle-types")

    generation_order = tuple(flows_vph)
    counts = [int(DURATION_S / 3600 * flows_vph[name]) for name in generation_order]
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
        "flows_vph": flows_vph,
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


def generate_eval7_flow_sweep_records(seed, requesting_flow, accepting_flow=1000):
    """Build nested Eval.7 inputs while keeping the mainline stream identical."""
    if accepting_flow != 1000 or not 0 <= requesting_flow <= 1000:
        raise ValueError(
            "Eval.7 flow-sweep generation requires accepting=1000 and "
            "requesting between 0 and 1000 veh/h"
        )
    master = generate_records("eval7", seed)
    if requesting_flow == 1000:
        return master

    accepting = [dict(record) for record in master[1:]
                 if record["approach"] == "accepting"]
    requesting_master = [dict(record) for record in master[1:]
                         if record["approach"] == "requesting"]
    requesting_count = int(DURATION_S / 3600 * requesting_flow)

    # One seed-specific ordering makes lower-flow schedules strict subsets of
    # higher-flow schedules instead of independently redrawing arrival times.
    selection_order = list(range(len(requesting_master)))
    selection_rng = random.Random(f"{seed}:eval7-requesting-flow-sweep")
    selection_rng.shuffle(selection_order)
    selected_indices = set(selection_order[:requesting_count])
    requesting = [record for index, record in enumerate(requesting_master)
                  if index in selected_indices]

    target_bus_count = int((len(accepting) + len(requesting)) * BUS_SHARE + 0.5)
    accepting_bus_count = sum(
        record["vehicle_type"] == "Bus" for record in accepting
    )
    requesting_bus_count = target_bus_count - accepting_bus_count
    if not 0 <= requesting_bus_count <= len(requesting):
        raise ValueError("fixed mainline bus count cannot satisfy requested total bus share")
    type_order = list(range(len(requesting)))
    type_rng = random.Random(f"{seed}:eval7-flow-sweep-types:{requesting_flow}")
    type_rng.shuffle(type_order)
    bus_indices = set(type_order[:requesting_bus_count])
    for index, record in enumerate(requesting):
        record["vehicle_type"] = "Bus" if index in bus_indices else "Car"

    approach_rank = {
        name: index for index, name in enumerate(CASE_SPECS["eval7"]["approach_order"])
    }
    events = sorted(
        accepting + requesting,
        key=lambda record: (record["depart_time_s"], approach_rank[record["approach"]]),
    )
    for sequence, record in enumerate(events):
        record["sequence"] = sequence
    metadata = dict(master[0])
    metadata["flows_vph"] = {
        "requesting": requesting_flow,
        "accepting": accepting_flow,
    }
    return [metadata, *events]


def serialize(records):
    return "".join(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n" for record in records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "fixed_inputs" / "thesis")
    parser.add_argument(
        "--seeds", type=int, nargs="+",
        help="generate this explicit seed set for every case instead of the development seeds")
    parser.add_argument(
        "--cases", choices=CASES, nargs="+", default=list(CASES),
        help="generate only these cases (default: all)")
    parser.add_argument(
        "--eval7-requesting-flows", type=int, nargs="+",
        help="generate an Eval.7 flow sweep under eval7-flow-sweep/")
    parser.add_argument(
        "--eval7-accepting-flow", type=int, default=1000,
        help="mainline flow used with --eval7-requesting-flows (default: 1000)")
    parser.add_argument("--check", action="store_true", help="fail if committed files differ")
    args = parser.parse_args()
    if args.seeds is not None and (
            any(seed < 0 for seed in args.seeds) or
            len(set(args.seeds)) != len(args.seeds)):
        parser.error("--seeds must be unique non-negative integers")
    if args.eval7_requesting_flows is not None:
        flows = args.eval7_requesting_flows + [args.eval7_accepting_flow]
        if "eval7" not in args.cases:
            parser.error("--eval7-requesting-flows requires --cases eval7")
        if args.eval7_accepting_flow != 1000 or any(
                flow < 0 or flow > 1000 for flow in args.eval7_requesting_flows):
            parser.error(
                "the nested Eval.7 sweep requires accepting=1000 and "
                "requesting flows between 0 and 1000 veh/h")
        if len(set(args.eval7_requesting_flows)) != len(args.eval7_requesting_flows):
            parser.error("--eval7-requesting-flows must be unique")
    failures = []
    for case_name in args.cases:
        case = CASES[case_name]
        if case_name == "eval7" and args.eval7_requesting_flows is not None:
            conditions = [
                ({"requesting": requesting, "accepting": args.eval7_accepting_flow},
                 args.output / "eval7-flow-sweep" /
                 f"requesting-{requesting}-accepting-{args.eval7_accepting_flow}")
                for requesting in args.eval7_requesting_flows
            ]
        else:
            conditions = [(None, args.output / case_name)]
        for seed in (args.seeds if args.seeds is not None else case["seeds"]):
            for flows_vph, output in conditions:
                path = output / f"seed-{seed}.jsonl"
                if case_name == "eval7" and flows_vph is not None:
                    expected = serialize(generate_eval7_flow_sweep_records(
                        seed,
                        flows_vph["requesting"],
                        flows_vph["accepting"],
                    ))
                else:
                    expected = serialize(generate_records(case_name, seed, flows_vph))
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

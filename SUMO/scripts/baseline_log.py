#!/usr/bin/env python3

import argparse
import os
import sys

from scenario_state import (
    DEACTIVATE_DISTANCE,
    OBSERVABLE_DISTANCE,
    build_scenario_state,
)
from summary_metrics import build_run_summary, dump_summary, format_distance

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)


def _load_traci():
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        tools = os.path.join(sumo_home, "tools")
        if tools not in sys.path:
            sys.path.append(tools)

    try:
        import traci  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Could not import traci. Check SUMO_HOME and SUMO Python tools."
        ) from exc

    return traci


def parse_args():
    parser = argparse.ArgumentParser(
        description="Log baseline vehicle speeds without cooperative control"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Run with sumo-gui instead of sumo",
    )
    parser.add_argument(
        "--config",
        default=os.path.join(PROJECT_ROOT, "cfg", "ramp.sumocfg"),
        help="Path to the SUMO config file",
    )
    parser.add_argument(
        "--summary-json",
        help="Optional path to save baseline summary metrics as JSON",
    )
    return parser.parse_args()


def run_baseline(traci, summary_json_path=None):
    vehicle_ids = ["MV1", "MV2", "RV"]
    phase_first_seen = {}
    event_times = {}
    metric_samples = {
        "mv2_speed_deactivate_to_merge": [],
        "rv_speed_observable_to_merge": [],
        "rv_abs_advisory_mismatch": [],
    }

    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        state = build_scenario_state(traci, vehicle_ids)
        if not state["all_present"]:
            continue

        sim_time = state["time"]
        phase = state["phase"]
        phase_first_seen.setdefault(phase, sim_time)

        rv_merge_dist = state["vehicles"]["RV"]["distance_to_merge"]
        mv2_merge_dist = state["vehicles"]["MV2"]["distance_to_merge"]
        if mv2_merge_dist is not None and 0.0 <= mv2_merge_dist <= DEACTIVATE_DISTANCE:
            metric_samples["mv2_speed_deactivate_to_merge"].append(
                state["vehicles"]["MV2"]["speed"]
            )
        if rv_merge_dist is not None and 0.0 <= rv_merge_dist <= OBSERVABLE_DISTANCE:
            metric_samples["rv_speed_observable_to_merge"].append(
                state["vehicles"]["RV"]["speed"]
            )

        if int(sim_time * 10) % 10 == 0:
            speeds = {
                veh_id: round(state["vehicles"][veh_id]["speed"], 2)
                for veh_id in vehicle_ids
            }
            merge_distances = {
                veh_id: format_distance(state["vehicles"][veh_id]["distance_to_merge"])
                for veh_id in vehicle_ids
            }
            print(f"t={sim_time:>4.1f}s phase={phase} dist={merge_distances} speeds={speeds}")

    run_summary = build_run_summary(phase_first_seen, event_times, metric_samples)
    dump_summary(run_summary, summary_json_path=summary_json_path)


def main():
    args = parse_args()
    traci = _load_traci()

    sumo_binary = "sumo-gui" if args.gui else "sumo"
    sumo_cmd = [sumo_binary, "-c", args.config]

    traci.start(sumo_cmd)
    try:
        run_baseline(traci, summary_json_path=args.summary_json)
    finally:
        traci.close()


if __name__ == "__main__":
    main()

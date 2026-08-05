#!/usr/bin/env python3

import argparse
import json
import os
import sys

from cloud_controller import CloudController
from scenario_state import (
    DEACTIVATE_DISTANCE,
    OBSERVABLE_DISTANCE,
    build_scenario_state,
)
from summary_metrics import build_run_summary, dump_summary, format_distance

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)


def load_traci():
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
        description="Run a V2C-style cooperative control skeleton"
    )
    parser.add_argument(
        "--nogui",
        action="store_true",
        help="Run with sumo instead of sumo-gui",
    )
    parser.add_argument(
        "--config",
        default=os.path.join(PROJECT_ROOT, "cfg", "ramp.sumocfg"),
        help="Path to the SUMO config file",
    )
    parser.add_argument(
        "--summary-json",
        help="Optional path to save run summary metrics as JSON",
    )
    parser.add_argument(
        "--controller-config",
        default=os.path.join(BASE_DIR, "controller_params.json"),
        help="Path to controller parameter JSON",
    )
    return parser.parse_args()


def load_controller_params(path):
    if not path:
        return {}
    if not os.path.exists(path):
        raise SystemExit(f"Controller config not found: {path}")
    with open(path, "r", encoding="utf-8") as config_file:
        return json.load(config_file)


def set_vehicle_defaults(traci, veh_id):
    traci.vehicle.setSpeedMode(veh_id, 0)
    traci.vehicle.setLaneChangeMode(veh_id, 0)


def apply_commands(traci, commands):
    for veh_id, command in commands.items():
        target_speed = command.get("target_speed")
        if target_speed is None:
            continue

        if target_speed < 0:
            traci.vehicle.setSpeed(veh_id, -1)
        else:
            transition_time = command.get("transition_time", 1.0)
            traci.vehicle.slowDown(veh_id, target_speed, transition_time)


def run_control(traci, controller_params=None, summary_json_path=None):
    controller = CloudController(params=controller_params)
    vehicle_ids = ["MV1", "MV2", "RV"]
    initialized = set()
    phase_first_seen = {}
    event_times = {}
    last_phase = None
    last_leader_for_mv2 = None
    last_flag2 = None
    last_release_hold_active = None
    metric_samples = {
        "mv2_speed_deactivate_to_merge": [],
        "rv_speed_observable_to_merge": [],
        "rv_abs_advisory_mismatch": [],
    }

    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()

        for veh_id in traci.vehicle.getIDList():
            if veh_id not in initialized:
                set_vehicle_defaults(traci, veh_id)
                initialized.add(veh_id)

        state = build_scenario_state(traci, vehicle_ids)
        if not state["all_present"]:
            continue

        commands = controller.compute_commands(state)
        apply_commands(traci, commands)

        sim_time = state["time"]
        phase = state["phase"]
        control_state = state.get("control_state", {})
        leader_for_mv2 = control_state.get(
            "leader_for_mv2", state["relationships"].get("leader_for_mv2")
        )
        flag2 = control_state.get("flag2")
        release_hold_active = control_state.get("release_hold_active")
        monitor_active = control_state.get("monitor_active")
        advisory_target_speeds = control_state.get("advisory_target_speeds", {})
        rv_cmd_speed = advisory_target_speeds.get("RV")
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
        if monitor_active and rv_cmd_speed is not None:
            metric_samples["rv_abs_advisory_mismatch"].append(
                abs(rv_cmd_speed - state["vehicles"]["RV"]["speed"])
            )

        if phase not in phase_first_seen:
            phase_first_seen[phase] = sim_time
        if last_phase is not None and phase != last_phase:
            event_times[f"{last_phase}_to_{phase}"] = sim_time
        if last_flag2 != 1 and flag2 == 1 and "flag2_activated" not in event_times:
            event_times["flag2_activated"] = sim_time
        if (
            last_leader_for_mv2 != "RV"
            and leader_for_mv2 == "RV"
            and "leader_switch_to_rv" not in event_times
        ):
            event_times["leader_switch_to_rv"] = sim_time
        if (
            last_release_hold_active is True
            and release_hold_active is False
            and "release_hold_finished" not in event_times
        ):
            event_times["release_hold_finished"] = sim_time

        last_phase = phase
        last_leader_for_mv2 = leader_for_mv2
        last_flag2 = flag2
        last_release_hold_active = release_hold_active

        if int(sim_time * 10) % 10 == 0:
            speeds = {
                veh_id: round(state["vehicles"][veh_id]["speed"], 2)
                for veh_id in vehicle_ids
            }
            merge_distances = {
                veh_id: format_distance(state["vehicles"][veh_id]["distance_to_merge"])
                for veh_id in vehicle_ids
            }
            interacting_distances = {
                veh_id: format_distance(
                    state["vehicles"][veh_id]["distance_to_interacting_zone"]
                )
                for veh_id in vehicle_ids
            }
            activation_ratio = control_state.get("activation_ratio")
            deactivation_ratio = control_state.get("deactivation_ratio")
            rv_adv = control_state.get("rv_advisory_accel")
            rv_speed_exceeded = control_state.get("rv_advisory_speed_exceeded")
            advisory_refresh = control_state.get("advisory_refresh")
            raw_target_speeds = control_state.get("raw_target_speeds", {})
            predicted_errors = control_state.get("predicted_errors", {})
            gamma_values = control_state.get("gamma_values", {})
            release_hold_active = control_state.get("release_hold_active")
            release_hold_elapsed = control_state.get("release_hold_elapsed")
            print(
                f"t={sim_time:>4.1f}s phase={phase} flag2={flag2} "
                f"leader(MV2)={leader_for_mv2} "
                f"monitor={monitor_active} refresh={advisory_refresh} "
                f"act={activation_ratio} deact={deactivation_ratio} "
                f"rv_adv={rv_adv} rv_over_limit={rv_speed_exceeded} "
                f"raw={raw_target_speeds} cmd={advisory_target_speeds} "
                f"gamma={gamma_values} err={predicted_errors} "
                f"release_hold={release_hold_active}/{release_hold_elapsed} "
                f"d2i={interacting_distances} dist={merge_distances} speeds={speeds}"
            )

    run_summary = build_run_summary(phase_first_seen, event_times, metric_samples)
    dump_summary(run_summary, summary_json_path=summary_json_path)


def main():
    args = parse_args()
    traci = load_traci()
    controller_params = load_controller_params(args.controller_config)

    sumo_binary = "sumo" if args.nogui else "sumo-gui"
    sumo_cmd = [sumo_binary, "-c", args.config]

    traci.start(sumo_cmd)
    try:
        run_control(
            traci,
            controller_params=controller_params,
            summary_json_path=args.summary_json,
        )
    finally:
        traci.close()


if __name__ == "__main__":
    main()

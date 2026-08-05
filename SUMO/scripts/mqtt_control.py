#!/usr/bin/env python3
"""Run the cooperative merging scenario through an MQTT V2C path."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from typing import Any

import paho.mqtt.client as mqtt

from control import apply_commands, load_controller_params, load_traci, set_vehicle_defaults
from scenario_state import DEACTIVATE_DISTANCE, OBSERVABLE_DISTANCE, build_scenario_state
from summary_metrics import build_run_summary, dump_summary, format_distance

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
VEHICLE_IDS = ("MV1", "MV2", "RV")


def frame_key(sim_time: float) -> str:
    return f"{sim_time:.3f}"


class MqttVehicleAdapter:
    """The simulated vehicle-side V2C terminal between TraCI and MQTT."""

    def __init__(
        self, host: str, port: int, run_id: str, qos: int, timeout_seconds: float
    ) -> None:
        self.host = host
        self.port = port
        self.run_id = run_id
        self.qos = qos
        self.timeout_seconds = timeout_seconds
        self.connected = threading.Event()
        self.lock = threading.Condition()
        self.responses: dict[str, dict[str, Any]] = {}
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"v2c-sumo-{run_id}"
        )
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        connect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        if reason_code.is_failure:
            raise RuntimeError(f"MQTT connection rejected: {reason_code}")
        client.subscribe(f"v2c/{self.run_id}/cloud/commands", qos=1)
        self.connected.set()
        print(f"vehicle adapter connected to mqtt://{self.host}:{self.port}", flush=True)

    def on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            key = frame_key(float(payload["sim_time"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"vehicle adapter ignored invalid command: {exc}", flush=True)
            return
        with self.lock:
            self.responses[key] = payload
            self.lock.notify_all()

    def connect(self) -> None:
        while True:
            try:
                self.client.connect(self.host, self.port, keepalive=30)
                break
            except OSError as exc:
                print(f"vehicle adapter waiting for broker: {exc}", flush=True)
                time.sleep(1)
        self.client.loop_start()
        if not self.connected.wait(timeout=15):
            raise TimeoutError("timed out while connecting the vehicle adapter to MQTT")

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def exchange(self, state: dict[str, Any]) -> dict[str, Any] | None:
        sim_time = float(state["time"])
        key = frame_key(sim_time)
        for vehicle_id in VEHICLE_IDS:
            payload = {
                "type": "vehicle_state",
                "run_id": self.run_id,
                "vehicle_id": vehicle_id,
                "sim_time": sim_time,
                "step_length": state["step_length"],
                "state": state["vehicles"][vehicle_id],
            }
            info = self.client.publish(
                f"v2c/{self.run_id}/vehicle/{vehicle_id}/state",
                json.dumps(payload, separators=(",", ":")),
                qos=self.qos,
            )
            info.wait_for_publish(timeout=self.timeout_seconds)

        deadline = time.monotonic() + self.timeout_seconds
        with self.lock:
            while key not in self.responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.lock.wait(timeout=remaining)
            return self.responses.pop(key)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ramp-merging controller through MQTT V2C communication"
    )
    parser.add_argument("--nogui", action="store_true", help="Run headless SUMO")
    parser.add_argument(
        "--config",
        default=os.path.join(PROJECT_ROOT, "cfg", "ramp.sumocfg"),
        help="Path to the SUMO configuration",
    )
    parser.add_argument("--summary-json", help="Path to write the run summary JSON")
    parser.add_argument(
        "--mqtt-host", default=os.environ.get("MQTT_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--mqtt-port", type=int, default=int(os.environ.get("MQTT_PORT", "1883"))
    )
    parser.add_argument("--qos", choices=(0, 1), type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=1.0)
    parser.add_argument("--run-id", default=f"run-{uuid.uuid4().hex[:8]}")
    return parser.parse_args()


def run_control(
    traci: Any, adapter: MqttVehicleAdapter, summary_json_path: str | None = None
) -> None:
    initialized: set[str] = set()
    phase_first_seen: dict[str, float] = {}
    event_times: dict[str, float] = {}
    last_phase: str | None = None
    last_leader_for_mv2: str | None = None
    last_flag2: int | None = None
    metric_samples = {
        "mv2_speed_deactivate_to_merge": [],
        "rv_speed_observable_to_merge": [],
        "rv_abs_advisory_mismatch": [],
    }
    communication = {"frames": 0, "timeouts": 0}

    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        for vehicle_id in traci.vehicle.getIDList():
            if vehicle_id not in initialized:
                set_vehicle_defaults(traci, vehicle_id)
                initialized.add(vehicle_id)

        state = build_scenario_state(traci, VEHICLE_IDS)
        if not state["all_present"]:
            continue

        sim_time = state["time"]
        if state["phase"] not in phase_first_seen:
            phase_first_seen[state["phase"]] = sim_time
        if last_phase is not None and state["phase"] != last_phase:
            event_times[f"{last_phase}_to_{state['phase']}"] = sim_time
        last_phase = state["phase"]

        rv_merge_dist = state["vehicles"]["RV"]["distance_to_merge"]
        mv2_merge_dist = state["vehicles"]["MV2"]["distance_to_merge"]
        if mv2_merge_dist is not None and 0 <= mv2_merge_dist <= DEACTIVATE_DISTANCE:
            metric_samples["mv2_speed_deactivate_to_merge"].append(
                state["vehicles"]["MV2"]["speed"]
            )
        if rv_merge_dist is not None and 0 <= rv_merge_dist <= OBSERVABLE_DISTANCE:
            metric_samples["rv_speed_observable_to_merge"].append(
                state["vehicles"]["RV"]["speed"]
            )

        response = adapter.exchange(state)
        communication["frames"] += 1
        if response is None:
            communication["timeouts"] += 1
            continue

        commands = response["commands"]
        control_state = response.get("control_state", {})
        apply_commands(traci, commands)
        flag2 = control_state.get("flag2")
        leader_for_mv2 = control_state.get(
            "leader_for_mv2", state["relationships"].get("leader_for_mv2")
        )
        if last_flag2 != 1 and flag2 == 1 and "flag2_activated" not in event_times:
            event_times["flag2_activated"] = sim_time
        if (
            last_leader_for_mv2 != "RV"
            and leader_for_mv2 == "RV"
            and "leader_switch_to_rv" not in event_times
        ):
            event_times["leader_switch_to_rv"] = sim_time
        last_flag2 = flag2
        last_leader_for_mv2 = leader_for_mv2

        rv_command = commands.get("RV", {}).get("target_speed")
        if rv_command is not None and rv_command >= 0:
            metric_samples["rv_abs_advisory_mismatch"].append(
                abs(rv_command - state["vehicles"]["RV"]["speed"])
            )

        if int(sim_time * 10) % 10 == 0:
            speeds = {
                vehicle_id: round(state["vehicles"][vehicle_id]["speed"], 2)
                for vehicle_id in VEHICLE_IDS
            }
            merge_distances = {
                vehicle_id: format_distance(state["vehicles"][vehicle_id]["distance_to_merge"])
                for vehicle_id in VEHICLE_IDS
            }
            print(
                f"t={sim_time:>4.1f}s phase={state['phase']} "
                f"flag2={flag2} leader(MV2)={leader_for_mv2} "
                f"dist={merge_distances} "
                f"speeds={speeds}",
                flush=True,
            )

    summary = build_run_summary(phase_first_seen, event_times, metric_samples)
    summary["communication"] = communication
    dump_summary(summary, summary_json_path=summary_json_path)


def main() -> None:
    args = parse_args()
    if not os.path.exists(os.path.join(PROJECT_ROOT, "net", "ramp.net.xml")):
        raise SystemExit("SUMO/net/ramp.net.xml is missing. Run netconvert before starting.")

    traci = load_traci()
    sumo_binary = "sumo" if args.nogui else "sumo-gui"
    adapter = MqttVehicleAdapter(
        args.mqtt_host, args.mqtt_port, args.run_id, args.qos, args.timeout_seconds
    )
    adapter.connect()
    traci.start([sumo_binary, "-c", args.config])
    try:
        run_control(traci, adapter, summary_json_path=args.summary_json)
    finally:
        traci.close()
        adapter.close()


if __name__ == "__main__":
    main()

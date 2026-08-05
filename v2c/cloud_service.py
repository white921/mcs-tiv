"""Cloud-side MQTT service for the SUMO V2C ramp-merging experiment.

The service receives one state message per simulated vehicle.  Once a complete
snapshot has arrived, it runs the existing cooperative-merging controller and
publishes a command frame for the vehicle-side SUMO adapter.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from typing import Any

import paho.mqtt.client as mqtt

from SUMO.scripts.cloud_controller import CloudController
from SUMO.scripts.scenario_state import (
    DEACTIVATE_DISTANCE,
    MAIN_PRE_LENGTH,
    MAIN_MERGE_LENGTH,
    MERGE_POINT_MAIN_POS,
    OBSERVABLE_DISTANCE,
    RAMP_TOTAL_LENGTH,
    infer_mv2_leader,
    infer_phase,
)

VEHICLE_IDS = ("MV1", "MV2", "RV")
STATE_TOPIC = "v2c/+/vehicle/+/state"


def frame_key(sim_time: float) -> str:
    return f"{sim_time:.3f}"


def build_cloud_state(
    vehicles: dict[str, dict[str, Any]], sim_time: float, step_length: float
) -> dict[str, Any]:
    """Rebuild the controller input from the three individual V2C messages."""
    relationships = {
        "mainline_gap": vehicles["MV1"]["x"] - vehicles["MV2"]["x"],
        "rv_to_mv1": vehicles["MV1"]["x"] - vehicles["RV"]["x"],
        "rv_to_mv2": vehicles["RV"]["x"] - vehicles["MV2"]["x"],
        "rv_merge_dist": vehicles["RV"]["distance_to_merge"],
        "mv2_merge_dist": vehicles["MV2"]["distance_to_merge"],
        "mv1_d2i": vehicles["MV1"]["distance_to_interacting_zone"],
        "rv_d2i": vehicles["RV"]["distance_to_interacting_zone"],
        "leader_for_mv2": infer_mv2_leader(vehicles),
    }
    return {
        "time": sim_time,
        "phase": infer_phase(vehicles),
        "all_present": True,
        "vehicles": vehicles,
        "relationships": relationships,
        "merge_point_main_pos": MERGE_POINT_MAIN_POS,
        "ramp_total_length": RAMP_TOTAL_LENGTH,
        "observable_distance": OBSERVABLE_DISTANCE,
        "deactivate_distance": DEACTIVATE_DISTANCE,
        "step_length": step_length,
    }


class CloudService:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.controllers: dict[str, CloudController] = {}
        self.pending: dict[str, dict[str, dict[str, dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        self.lock = threading.Lock()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="v2c-cloud-controller"
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
        client.subscribe(STATE_TOPIC, qos=1)
        print(f"cloud connected to mqtt://{self.host}:{self.port}", flush=True)

    def on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            run_id = payload["run_id"]
            vehicle_id = payload["vehicle_id"]
            sim_time = float(payload["sim_time"])
            state = payload["state"]
            step_length = float(payload["step_length"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"cloud ignored invalid state message: {exc}", flush=True)
            return

        if vehicle_id not in VEHICLE_IDS:
            print(f"cloud ignored unknown vehicle: {vehicle_id}", flush=True)
            return

        key = frame_key(sim_time)
        with self.lock:
            frame = self.pending[run_id][key]
            frame[vehicle_id] = state
            if not all(vehicle in frame for vehicle in VEHICLE_IDS):
                return
            vehicles = {vehicle: frame[vehicle] for vehicle in VEHICLE_IDS}
            del self.pending[run_id][key]
            self._discard_old_frames(run_id, key)
            controller = self.controllers.setdefault(run_id, CloudController())

        cloud_state = build_cloud_state(vehicles, sim_time, step_length)
        commands = controller.compute_commands(cloud_state)
        response = {
            "type": "commands",
            "run_id": run_id,
            "sim_time": sim_time,
            "commands": commands,
            "control_state": cloud_state.get("control_state", {}),
        }
        client.publish(
            f"v2c/{run_id}/cloud/commands",
            json.dumps(response, separators=(",", ":")),
            qos=1,
        )

    def _discard_old_frames(self, run_id: str, completed_key: str) -> None:
        """A late partial snapshot must not become a command later in the run."""
        completed_time = float(completed_key)
        stale = [
            key
            for key in self.pending[run_id]
            if float(key) < completed_time
        ]
        for key in stale:
            del self.pending[run_id][key]

    def run_forever(self) -> None:
        while True:
            try:
                self.client.connect(self.host, self.port, keepalive=30)
                break
            except OSError as exc:
                print(f"cloud waiting for broker: {exc}", flush=True)
                time.sleep(1)
        self.client.loop_forever()


def main() -> None:
    host = os.environ.get("MQTT_HOST", "127.0.0.1")
    port = int(os.environ.get("MQTT_PORT", "1883"))
    CloudService(host, port).run_forever()


if __name__ == "__main__":
    main()

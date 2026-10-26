import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
sys.path.insert(0, str(ROOT / "scripts"))

import diagnostic_trace
import run_thesis_batch


class FakeVehicleAPI:
    def getLeader(self, vehicle_id):
        return ("lead-1", 7.5)

    def getLaneID(self, vehicle_id):
        return "left_0"

    def getPosition(self, vehicle_id):
        return (149.0, -1.6)

    def getRouteID(self, vehicle_id):
        return "BL"

    def getRoadID(self, vehicle_id):
        return "bottom"

    def getSpeed(self, vehicle_id):
        return 4.0

    def getAngle(self, vehicle_id):
        return 90.0

    def getSlope(self, vehicle_id):
        return 0.0

    def getLength(self, vehicle_id):
        return 5.0

    def getWidth(self, vehicle_id):
        return 1.8

    def getHeight(self, vehicle_id):
        return 1.5

    def getLanePosition(self, vehicle_id):
        return 42.0

    def getLateralLanePosition(self, vehicle_id):
        return 0.0

    def getSignals(self, vehicle_id):
        return 10  # left blinker + brake light

    def getColor(self, vehicle_id):
        return (20, 30, 40, 255)


class DiagnosticTraceTests(unittest.TestCase):
    def setUp(self):
        diagnostic_trace.close()
        self.temp = tempfile.TemporaryDirectory()
        directory = Path(self.temp.name)
        diagnostic_trace.STATE_AUDIT = str(directory / "states.jsonl")
        diagnostic_trace.CONFLICT_AUDIT = str(directory / "conflicts.jsonl")
        diagnostic_trace.NEGOTIATION_AUDIT = str(directory / "negotiations.jsonl")
        diagnostic_trace.RUNTIME_AUDIT = str(directory / "runtime.jsonl")
        self.directory = directory

    def tearDown(self):
        diagnostic_trace.close()
        self.temp.cleanup()

    def _vehicle(self):
        path = SimpleNamespace(pathID="1_4", vehID="1", type="planned", t=[10.0])
        return SimpleNamespace(
            id="1", type="Car", typeID="CAV_0", pos_x=145.0, pos_y=-1.6,
            speed=5.0, accel=-1.0, route="LR", road="left", lane=0,
            status="yield", passjunctionstatus="before", plannedPath=path,
            desiredPaths=[], leadPath=None, isWaitAgree=False, waitPath=None,
            waitAgreeID=[], receiveAgreeID=[], simTime=10.0,
            alter_straight_path=None)

    def test_vehicle_state_frame_contains_replay_fields(self):
        vehicle = self._vehicle()
        traci = SimpleNamespace(vehicle=FakeVehicleAPI())

        diagnostic_trace.record_vehicle_states([vehicle], 10.0, traci)
        diagnostic_trace.close()

        record = json.loads((self.directory / "states.jsonl").read_text())
        state = record["vehicles"][0]
        self.assertEqual(record["record_type"], "vehicle_state_frame")
        self.assertEqual(state["vehicle_id"], "1")
        self.assertEqual(state["leader_id"], "lead-1")
        self.assertEqual(state["leader_gap_m"], 7.5)
        self.assertEqual(state["planned_path_id"], "1_4")
        self.assertEqual(state["angle_deg"], 90.0)
        self.assertEqual(state["signals"], 10)
        self.assertTrue(state["signal_state"]["left_blinker"])
        self.assertTrue(state["signal_state"]["brake_light"])
        self.assertFalse(state["signal_state"]["right_blinker"])
        self.assertEqual(state["length_m"], 5.0)
        self.assertEqual(state["color_rgba"], [20, 30, 40, 255])

    def test_initialize_creates_zero_event_streams(self):
        diagnostic_trace.initialize()
        diagnostic_trace.close()

        self.assertEqual((self.directory / "conflicts.jsonl").read_text(), "")
        self.assertEqual((self.directory / "negotiations.jsonl").read_text(), "")

    def test_conflict_negotiation_and_runtime_are_time_joinable(self):
        vehicle = self._vehicle()
        traci = SimpleNamespace(vehicle=FakeVehicleAPI())
        own = vehicle.plannedPath
        other = SimpleNamespace(
            pathID="43_7", vehID="43", type="desired", t=[10.0])
        collision = {"collide_x": 149.0, "collide_y": -1.6, "duration": 2.4}

        diagnostic_trace.record_conflict(
            vehicle, own, other, collision, traci,
            own_pass_time=12.0, other_pass_time=11.0, pet_s=1.0,
            reason="pet", check_type="desired")
        diagnostic_trace.record_negotiation(
            vehicle, other, "decision", accept=True, reason="test",
            collision=collision)
        diagnostic_trace.record_runtime(
            10.0, {"sumo_step": 0.01}, 1, 0.02)
        diagnostic_trace.close()

        conflict = json.loads((self.directory / "conflicts.jsonl").read_text())
        negotiation = json.loads((self.directory / "negotiations.jsonl").read_text())
        runtime = json.loads((self.directory / "runtime.jsonl").read_text())
        self.assertEqual(conflict["sim_time"], negotiation["sim_time"])
        self.assertEqual(conflict["sim_time"], runtime["sim_time"])
        self.assertEqual(conflict["pet_s"], 1.0)
        self.assertEqual(conflict["other_position"], [149.0, -1.6])
        self.assertEqual(conflict["other_distance_to_conflict_m"], 0.0)
        self.assertTrue(negotiation["accept"])

    def test_source_hashes_ignore_runtime_statistics(self):
        source = self.directory / "source"
        (source / "func").mkdir(parents=True)
        (source / "junction" / "statistics").mkdir(parents=True)
        (source / "func" / "model.py").write_text("VALUE = 1\n")
        (source / "junction" / "statistics" / "trip.xml").write_text("<trip/>\n")

        hashes = run_thesis_batch.source_hashes(source)

        self.assertEqual(list(hashes), ["func/model.py"])


if __name__ == "__main__":
    unittest.main()

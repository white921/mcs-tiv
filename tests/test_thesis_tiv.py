import copy
import math
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "func"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "PathPlanning" / "FrenetOptimalTrajectory"))
import thesis_tiv as tiv


def path(veh="1", kind="planned", speed=10, y=0):
    return NS(vehID=veh, type=kind, pathID=veh + "_1",
              t=[i / 10 for i in range(101)],
              x=[i / 10 * speed for i in range(101)],
              y=[y] * 101, s_d=[speed] * 101, negotiationID=["2"])


def region(x=20, y=0):
    return {
        "schema_version": 1,
        "center_x_m": x,
        "center_y_m": y,
        "heading_rad": 0.0,
        "longitudinal_radius_m": 0.01,
        "lateral_radius_m": 0.01,
        "horizon_s": 10.0,
    }


def vehicle(veh="1"):
    return NS(id=veh, typeID="Car", alpha=7, angle=90, simTime=0,
              pos_x=0, pos_y=0, receivedPaths=[], plannedPath=path(veh),
              desiredPaths=[], alter_straight_path=None, alter_change_path=None,
              count_send_PT=0, count_send_DT=0, count_send_AT=0,
              count_refuse_physics=0, count_refuse_utility=0,
              count_accept_utility=0, WithAgreementPhase=False,
              isWaitAgree=False, yetJudgedList=[], road="receiver-road",
              pathID=1, status="free", leader=None, leadPath=None,
              waitPath=None, waitAgreeID=[], receiveAgreeID=[])


def traci():
    return NS(vehicle=NS(getAllowedSpeed=Mock(return_value=10),
                         getRoadID=Mock(return_value="sender-road"),
                         getLaneID=Mock(return_value="sender-road_1"),
                         getLaneIndex=Mock(return_value=1),
                         getLanePosition=Mock(return_value=12.5),
                         getSpeed=Mock(return_value=2),
                         getPosition=Mock(return_value=(0, 0)),
                         getLeader=Mock(return_value=None),
                         getFollower=Mock(return_value=("", -1))),
              vehicletype=NS(getAccel=Mock(return_value=3),
                             getMaxSpeed=Mock(return_value=12)))


class ThesisTIVTests(unittest.TestCase):
    def test_merge_negotiation_start_keeps_legacy_trigger_when_disabled(self):
        with patch.object(tiv, "MERGE_NEGOTIATION_LEAD_S", 0.0):
            self.assertEqual(
                tiv.merge_negotiation_start_position(
                    NS(allowed_speed_mps=13.89), 200, 300, 13.89),
                200.0)

    def test_merge_negotiation_start_uses_free_flow_deadline(self):
        with patch.object(tiv, "MERGE_NEGOTIATION_LEAD_S", 10.0):
            self.assertAlmostEqual(
                tiv.merge_negotiation_start_position(
                    NS(allowed_speed_mps=13.89), 200, 300, 13.89),
                161.1)

    def test_merge_negotiation_start_falls_back_to_map_speed(self):
        with patch.object(tiv, "MERGE_NEGOTIATION_LEAD_S", 10.0):
            self.assertAlmostEqual(
                tiv.merge_negotiation_start_position(
                    NS(allowed_speed_mps=None), 200, 300, 10.0),
                200.0)

    def test_two_stage_blocks_merge_execution_before_legacy_trigger(self):
        merging = NS(lane=0, pos_x=199.9)
        with patch.object(tiv, "TWO_STAGE_MERGE_NEGOTIATION", True):
            self.assertFalse(tiv.two_stage_merge_execution_allowed(merging))
            merging.pos_x = 200.0
            self.assertTrue(tiv.two_stage_merge_execution_allowed(merging))

    def test_two_stage_reserves_without_yield_then_activates_fresh_path(self):
        v, desired, collisions = self.decision()
        v.WithAgreementPhase = True
        v.lane = 0
        desired.lane_position = 160.0
        desired.negotiationID = ["2", "4"]
        collisions[0].update(collide_x=250.0, collide_y=-4.8)
        v.selectBestPath = lambda values: (None, values[0])

        with patch.object(tiv, "TWO_STAGE_MERGE_NEGOTIATION", True):
            tiv.judge_yield(v, collisions, [], traci(), merge=True)

            reservation = v._mcs_two_stage_merge_reservation
            self.assertEqual(reservation["sender"], "1")
            self.assertEqual(reservation["participants"], ("2", "4"))
            self.assertIsNone(v.alter_straight_path)
            self.assertFalse(v.isWaitAgree)
            self.assertNotEqual(v.status, "yield")

            refreshed = copy.deepcopy(desired)
            refreshed.pathID = "1_2"
            refreshed.lane_position = 199.9
            v.generateAlterPath.reset_mock()
            tiv.judge_yield(
                v, [{**collisions[0], "path": refreshed}], [], traci(),
                merge=True)
            v.generateAlterPath.assert_not_called()

            refreshed.pathID = "1_3"
            refreshed.lane_position = 200.0
            v.generateAlterPath.return_value = [path("2", "alter")]
            tiv.judge_yield(
                v, [{**collisions[0], "path": refreshed}], [], traci(),
                merge=True)

        self.assertIsNone(v._mcs_two_stage_merge_reservation)
        self.assertTrue(v.isWaitAgree)
        self.assertEqual(v.alter_straight_path.type, "alter")
        self.assertIs(v.waitPath, refreshed)

    def test_two_stage_releases_on_participant_change(self):
        v, desired, collisions = self.decision()
        v.WithAgreementPhase = True
        v.lane = 0
        desired.lane_position = 160.0
        desired.negotiationID = ["2"]
        v.selectBestPath = lambda values: (None, values[0])

        with patch.object(tiv, "TWO_STAGE_MERGE_NEGOTIATION", True):
            tiv.judge_yield(v, collisions, [], traci(), merge=True)
            changed = copy.deepcopy(desired)
            changed.pathID = "1_2"
            changed.negotiationID = ["2", "4"]
            result = tiv.reconcile_two_stage_merge_reservation(
                v, [{"path": changed}])

        self.assertIsNone(result)
        self.assertIsNone(v._mcs_two_stage_merge_reservation)

    def test_two_stage_releases_when_another_sender_conflicts(self):
        v, desired, collisions = self.decision()
        v.WithAgreementPhase = True
        v.lane = 0
        desired.lane_position = 160.0
        v.selectBestPath = lambda values: (None, values[0])

        with patch.object(tiv, "TWO_STAGE_MERGE_NEGOTIATION", True):
            tiv.judge_yield(v, collisions, [], traci(), merge=True)
            another = copy.deepcopy(desired)
            another.vehID = "3"
            another.pathID = "3_1"
            result = tiv.reconcile_two_stage_merge_reservation(
                v, [{"path": desired}, {"path": another}])

        self.assertIsNone(result)
        self.assertIsNone(v._mcs_two_stage_merge_reservation)

    def test_two_stage_releases_when_fresh_alternative_is_infeasible(self):
        v, desired, collisions = self.decision()
        v.WithAgreementPhase = True
        v.lane = 0
        desired.lane_position = 160.0
        v.selectBestPath = lambda values: (None, values[0])

        with patch.object(tiv, "TWO_STAGE_MERGE_NEGOTIATION", True):
            tiv.judge_yield(v, collisions, [], traci(), merge=True)
            refreshed = copy.deepcopy(desired)
            refreshed.pathID = "1_2"
            refreshed.lane_position = 200.0
            v.generateAlterPath.return_value = []
            tiv.judge_yield(
                v, [{"path": refreshed}], [], traci(), merge=True)

        self.assertIsNone(v._mcs_two_stage_merge_reservation)
        self.assertFalse(v.isWaitAgree)

    def test_vertical_opposing_lanes_are_not_treated_as_same_corridor(self):
        self.assertFalse(tiv.trajectories_are_too_close(
            148.4, 32, 151.6, 32,
            0, -5, 0, 5,
            5, 1.8, 1.5))

    def test_vertical_same_lane_close_vehicles_are_detected(self):
        self.assertTrue(tiv.trajectories_are_too_close(
            148.4, 32, 148.4, 36,
            0, -5, 0, -5,
            5, 1.8, 1.5))

    def test_horizontal_opposing_lanes_are_not_treated_as_same_corridor(self):
        self.assertFalse(tiv.trajectories_are_too_close(
            100, -1.6, 100, 1.6,
            5, 0, -5, 0,
            5, 1.8, 1.5))

    def test_point_one_second_trajectory_samples_keep_small_acceleration(self):
        import frenet_three_junction as planner
        with patch.dict(os.environ, {"MCS_TIV_IMPLEMENTATION": "thesis"}):
            paths = planner.calc_frenet_paths_free(0, 5, 0, 0, 0, 0)
        legal = [p for p in paths if max(p.s_d) <= 13.89 and
                 max(p.s_dd) <= 3 and min(p.s_dd) >= -5]
        best = min(legal, key=lambda p: p.cf)
        self.assertGreater((best.s[1] - best.s[0]) / .1, 5)
        self.assertEqual(round(best.s[1], 3) / .1, 5)

    def test_planned_update_interval_uses_archived_one_second_expiry(self):
        v = vehicle()
        self.assertEqual(tiv.planned_update_interval(v, .1), 1)
        v.alpha = 4
        self.assertEqual(tiv.planned_update_interval(v, 1), 1)

    def test_audit_handles_numpy_scalars(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            target = str(Path(directory) / "audit.json")
            with patch.dict(os.environ, {"MCS_TIV_AUDIT": target}), patch.object(
                tiv, "EXAMPLES", [{"accept": np.bool_(True), "value": np.float64(math.inf)}]
            ):
                tiv._write_audit()
            self.assertEqual(json.loads(Path(target).read_text())["examples"],
                             [{"accept": True, "value": "unreached"}])

    def test_equation_42_values(self):
        for x, expected in [(0, 1), (5, 1), (30, .9), (40, .756),
                            (70, .378), (100, 0), (120, 0)]:
            self.assertAlmostEqual(tiv.following_rate(x, 10), expected)

    def test_rate_invalid_arguments(self):
        for x, speed in [(-1, 10), (5, 0)]:
            with self.assertRaises(ValueError):
                tiv.following_rate(x, speed)

    def test_rate_stated_bounds(self):
        for speed in (5.56, 10, 11.11, 13.89, 25):
            for x in range(130):
                self.assertTrue(0 <= tiv.following_rate(x, speed) <= 1)

    def test_formula_own_vehicle_and_performance(self):
        v = vehicle()
        result = tiv.score(v, v.plannedPath, region(), 10, 3)
        self.assertAlmostEqual(result["value"], 2 - .1 * 10 + .1 * 3)
        self.assertAlmostEqual(
            tiv.score(v, v.plannedPath, region(), 10, 1)["value"], 1.1)
        v.alpha = 6
        self.assertAlmostEqual(
            tiv.score(v, v.plannedPath, region(), 10, 3)["value"], 1)

    def test_actual_followers_unique_planned_terminal_speed(self):
        v = vehicle()
        follower = path("2", speed=5)
        follower.x = [-30 + x for x in follower.x]
        follower.s_d[-1] = 7
        desire = copy.deepcopy(follower)
        desire.type = "desired"
        desire.s_d[-1] = 100
        adjacent = path("3", y=3.2)
        adjacent.x = [-30 + x for x in adjacent.x]
        v.receivedPaths = [follower, copy.deepcopy(follower), desire, adjacent,
                           v.plannedPath, path("ahead")]
        self.assertAlmostEqual(tiv.environmental_term(v, v.plannedPath, 10), 10 + .9 * 7)

    def test_horizon_uses_transmitted_not_unbounded_terminal(self):
        p = path()
        p.t += [10.1, 10.2]
        p.x += [101, 102]
        p.y += [0, 0]
        p.s_d += [99, 99]
        self.assertEqual(tiv.transmitted_path(p, 0).s_d[-1], 10)

    def test_snapshot_does_not_mutate_original(self):
        p = path()
        snapshot = tiv.transmitted_path(p, .1)
        snapshot.x[0] = 999
        self.assertEqual(p.x[1], 1)
        self.assertEqual(snapshot.t[0], .1)

    def test_snapshot_keeps_short_geometry_time_aligned(self):
        p = path()
        p.x = p.x[:-1]
        snapshot = tiv.transmitted_path(p, .1)
        self.assertEqual(len(snapshot.t), len(snapshot.x))
        self.assertEqual(len(snapshot.y), len(snapshot.x))
        self.assertEqual(snapshot.x[0], 1)

    def test_arrival_absolute_time_not_raw_index(self):
        p = path()
        p.t = [t + 5 for t in p.t]
        self.assertAlmostEqual(tiv.arrival_delay(p, region(), 5.1), 1.9)

    def test_missing_arrival_is_an_inconsistent_negotiation_event(self):
        with self.assertRaisesRegex(ValueError, "does not enter"):
            tiv.arrival_delay(path(speed=0), region(), 0)
        with self.assertRaisesRegex(ValueError, "does not enter"):
            tiv.arrival_delay(path(), region(200), 0)

    def test_packet_is_computed_by_sender_and_immutable(self):
        sender = vehicle()
        desired = path(kind="desired")
        sender.desiredPaths = [desired]
        sender.checkPathCollision = Mock(return_value=(
            [{"collideID": "2", "collide_x": 20, "collide_y": 0,
              "duration": 2.0, "path": path("2")}], []))
        server = []
        api = traci()
        tiv.send_mcm(sender, server, api)
        packet = server[1]
        self.assertAlmostEqual(
            packet.tiv_by_receiver["2"]["arrival_delay"], 0.5)
        self.assertAlmostEqual(packet.tiv_by_receiver["2"]["value"], -0.2)
        self.assertEqual(packet.tiv_by_receiver["2"]["region"]["schema_version"], 1)
        self.assertEqual(packet.road_id, "sender-road")
        self.assertEqual(packet.lane_id, "sender-road_1")
        self.assertEqual(packet.lane_index, 1)
        self.assertEqual(packet.lane_position, 12.5)
        self.assertEqual(packet.allowed_speed_mps, 10)
        self.assertEqual(sender.lane_id, "sender-road_1")
        self.assertEqual(sender.allowed_speed_mps, 10)
        desired.x[0] = 999
        self.assertEqual(packet.x[0], 0)
        api.vehicle.getAllowedSpeed.assert_called_once_with("1")

    def decision(self, desired_value=1.3):
        v = vehicle("2")
        desired = path("1", "desired")
        desired.tiv_by_receiver = {"2": {"value": desired_value, "point": (20, 0),
                                       "region": region(),
                                       "sender": "1", "path_id": desired.pathID,
                                       "sent_at": -.1}}
        v.generateAlterPath = Mock(return_value=[path("2", "alter")])
        v.selectBestPath = lambda values: values[0]
        return v, desired, [{"path": desired}]

    def test_figure42_accepts_equal_scores(self):
        v, _, collisions = self.decision()
        tiv.judge_yield(v, collisions, [], traci())
        self.assertEqual(v.count_accept_utility, 1)
        self.assertEqual(v.status, "yield")

    def test_receiver_uses_transmitted_number_not_recomputed_desired(self):
        v, desired, collisions = self.decision(999)
        desired.s_d[-1] = 9999
        api = traci()
        tiv.judge_yield(v, collisions, [], api)
        self.assertEqual(v.count_refuse_utility, 1)
        self.assertIsNone(v.alter_straight_path)
        api.vehicle.getAllowedSpeed.assert_called_once_with("2")

    def test_no_alternative_rejects_before_tiv(self):
        v, _, collisions = self.decision()
        v.generateAlterPath.return_value = []
        api = traci()
        tiv.judge_yield(v, collisions, [], api)
        self.assertEqual(v.count_refuse_physics, 1)
        api.vehicle.getAllowedSpeed.assert_not_called()

    def test_active_duplicate_decision_skips_same_desired_path(self):
        v, _, collisions = self.decision()
        with patch.object(tiv.deceleration_prediction,
                          "active_decision_is_locked", return_value=True):
            tiv.judge_yield(v, collisions, [], traci())
        v.generateAlterPath.assert_not_called()
        self.assertEqual(v.count_accept_utility, 0)
        self.assertEqual(v.count_refuse_utility, 0)

    def test_missing_sender_value_no_fallback_no_permanent_rejection(self):
        v, desired, collisions = self.decision()
        desired.tiv_by_receiver = {}
        tiv.judge_yield(v, collisions, [], traci())
        self.assertEqual(v.count_accept_utility, 0)
        self.assertEqual(v.yetJudgedList, [])
        self.assertIsNone(v.alter_straight_path)

    def test_agreement_retains_state_transition(self):
        v, desired, collisions = self.decision()
        v.WithAgreementPhase = True
        tiv.judge_yield(v, collisions, [], traci())
        self.assertTrue(v.isWaitAgree)
        self.assertEqual(v.alter_straight_path.type, "alter")
        self.assertIs(v.waitPath, desired)
        v.waitAgreeID.append("new")
        self.assertEqual(desired.negotiationID, ["2"])

    def test_agreement_lease_reuses_accept_for_same_physical_conflict(self):
        v, desired, collisions = self.decision()
        v.WithAgreementPhase = True
        collisions[0].update(collide_x=20, collide_y=0)
        with patch.object(tiv, "AGREEMENT_LEASE_S", 1.0):
            tiv.judge_yield(v, collisions, [], traci())
            self.assertTrue(v.isWaitAgree)
            original_expiry = v._mcs_agreement_lease["expires_at"]

            refreshed = copy.deepcopy(desired)
            refreshed.pathID = "1_2"
            refreshed.tiv_by_receiver = {}
            v.simTime = 0.9
            tiv.judge_yield(
                v, [{"path": refreshed, "collide_x": 20.5, "collide_y": 0}],
                [], traci())

        self.assertTrue(v.isWaitAgree)
        self.assertIs(v.waitPath, refreshed)
        self.assertEqual(v._mcs_agreement_lease["expires_at"], original_expiry)
        self.assertEqual(v.count_accept_utility, 2)

    def test_agreement_lease_does_not_cross_conflict_region(self):
        v, desired, collisions = self.decision()
        collisions[0].update(collide_x=20, collide_y=0)
        v._mcs_agreement_lease = {
            "sender": desired.vehID,
            "point": (20.0, 0.0),
            "accepted_at": 0.0,
            "expires_at": 1.0,
        }
        with patch.object(tiv, "AGREEMENT_LEASE_S", 1.0):
            self.assertFalse(tiv.agreement_lease_accepts(
                v, desired,
                {"path": desired, "collide_x": 23.0, "collide_y": 0}))

    def test_agreement_lease_expires_without_extension(self):
        v, desired, _ = self.decision()
        v.simTime = 1.1
        v._mcs_agreement_lease = {
            "sender": desired.vehID,
            "point": (20.0, 0.0),
            "accepted_at": 0.0,
            "expires_at": 1.0,
        }
        with patch.object(tiv, "AGREEMENT_LEASE_S", 1.0):
            self.assertFalse(tiv.agreement_lease_accepts(
                v, desired,
                {"path": desired, "collide_x": 20.0, "collide_y": 0}))
        self.assertIsNone(v._mcs_agreement_lease)

    def test_inconsistent_arrival_defers_without_synthetic_decision(self):
        v, _, collisions = self.decision(math.inf)
        v.plannedPath = path("2", speed=0)
        tiv.judge_yield(v, collisions, [], traci())
        self.assertEqual(v.count_refuse_utility, 0)
        self.assertEqual(v.count_accept_utility, 0)
        self.assertIsNone(v.alter_straight_path)

    def test_merge_selector_tuple(self):
        v, _, collisions = self.decision()
        v.lane = 0
        v.selectBestPath = lambda values: (None, values[0])
        tiv.judge_yield(v, collisions, [], traci(), merge=True)
        self.assertEqual(v.count_accept_utility, 1)


if __name__ == "__main__":
    unittest.main()

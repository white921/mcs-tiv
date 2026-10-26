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
                         getLaneIndex=Mock(return_value=1),
                         getSpeed=Mock(return_value=2),
                         getPosition=Mock(return_value=(0, 0)),
                         getLeader=Mock(return_value=None),
                         getFollower=Mock(return_value=("", -1))),
              vehicletype=NS(getAccel=Mock(return_value=3)))


class ThesisTIVTests(unittest.TestCase):
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
        result = tiv.score(v, v.plannedPath, (20, 0), 10, 3)
        self.assertAlmostEqual(result["value"], 2 - .1 * 10 + .1 * 3)
        self.assertAlmostEqual(tiv.score(v, v.plannedPath, (20, 0), 10, 1)["value"], 1.1)
        v.alpha = 6
        self.assertAlmostEqual(tiv.score(v, v.plannedPath, (20, 0), 10, 3)["value"], 1)

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
        self.assertAlmostEqual(tiv.arrival_delay(p, (20, 0), 5.1), 1.9)

    def test_unreachable_not_fictitious_arrival(self):
        self.assertEqual(tiv.arrival_delay(path(speed=0), (20, 0), 0), math.inf)
        self.assertEqual(tiv.arrival_delay(path(), (200, 0), 0), math.inf)

    def test_packet_is_computed_by_sender_and_immutable(self):
        sender = vehicle()
        desired = path(kind="desired")
        sender.desiredPaths = [desired]
        sender.checkPathCollision = Mock(return_value=(
            [{"collideID": "2", "collide_x": 20, "collide_y": 0}], []))
        server = []
        api = traci()
        tiv.send_mcm(sender, server, api)
        packet = server[1]
        self.assertAlmostEqual(packet.tiv_by_receiver["2"]["value"], 1.3)
        desired.x[0] = 999
        self.assertEqual(packet.x[0], 0)
        api.vehicle.getAllowedSpeed.assert_called_once_with("1")

    def decision(self, desired_value=1.3):
        v = vehicle("2")
        desired = path("1", "desired")
        desired.tiv_by_receiver = {"2": {"value": desired_value, "point": (20, 0),
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

    def test_conditional_hold_remembers_without_yielding_while_priority_blocked(self):
        v, desired, collisions = self.decision()
        collisions[0].update(collide_x=20, collide_y=0)
        v.WithAgreementPhase = True
        api = traci()
        api.vehicle.getLeader.return_value = ("24", 1.0)
        with patch.dict(os.environ, {"MCS_PRIORITY_HOLD_MODE": "conditional"}):
            tiv.judge_yield(v, collisions, [], api)
            self.assertEqual(v._mcs_priority_hold["phase"], "awaiting_agreement")
            v.receiveAgreeID = list(v.waitAgreeID)
            self.assertFalse(tiv.complete_conditional_agreement(v, [], api))
        self.assertEqual(v._mcs_priority_hold["phase"], "remembered")
        self.assertFalse(v.isWaitAgree)
        self.assertEqual(v.status, "free")
        self.assertIsNone(v.alter_straight_path)

    def test_conditional_hold_activates_after_priority_can_advance(self):
        v, desired, collisions = self.decision()
        collisions[0].update(collide_x=20, collide_y=0)
        v.WithAgreementPhase = True
        api = traci()
        api.vehicle.getLeader.return_value = ("24", 1.0)
        with patch.dict(os.environ, {"MCS_PRIORITY_HOLD_MODE": "conditional"}):
            tiv.judge_yield(v, collisions, [], api)
            v.receiveAgreeID = list(v.waitAgreeID)
            self.assertFalse(tiv.complete_conditional_agreement(v, [], api))
            refreshed = copy.deepcopy(desired)
            refreshed.pathID = "1_2"
            api.vehicle.getLeader.return_value = None
            v.generateAlterPath = Mock(return_value=[path("2", "alter")])
            tiv.judge_yield(v, [{"path": refreshed, "collide_x": 20,
                                 "collide_y": 0}], [], api)
        self.assertEqual(v._mcs_priority_hold["phase"], "active")
        self.assertEqual(v.status, "yield")
        self.assertEqual(v.leader, "1")
        self.assertEqual(v.plannedPath.type, "planned")

    def test_conditional_hold_releases_if_participants_change(self):
        v, desired, collisions = self.decision()
        collisions[0].update(collide_x=20, collide_y=0)
        v.WithAgreementPhase = True
        api = traci()
        api.vehicle.getLeader.return_value = ("24", 1.0)
        with patch.dict(os.environ, {"MCS_PRIORITY_HOLD_MODE": "conditional"}):
            tiv.judge_yield(v, collisions, [], api)
            v.receiveAgreeID = list(v.waitAgreeID)
            self.assertFalse(tiv.complete_conditional_agreement(v, [], api))
            changed = copy.deepcopy(desired)
            changed.pathID = "1_2"
            changed.negotiationID = ["2", "3"]
            self.assertEqual(
                tiv._release_reason(v, {"path": changed}, api),
                "conflict_participants_changed")

    def test_two_unreachable_paths_not_accepted(self):
        v, _, collisions = self.decision(math.inf)
        v.plannedPath = path("2", speed=0)
        tiv.judge_yield(v, collisions, [], traci())
        self.assertEqual(v.count_refuse_utility, 1)

    def test_merge_selector_tuple(self):
        v, _, collisions = self.decision()
        v.lane = 0
        v.selectBestPath = lambda values: (None, values[0])
        tiv.judge_yield(v, collisions, [], traci(), merge=True)
        self.assertEqual(v.count_accept_utility, 1)


if __name__ == "__main__":
    unittest.main()

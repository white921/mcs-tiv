import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "func"))
import deceleration_loss as loss
import deceleration_prediction as prediction


class DecelerationLossTests(unittest.TestCase):
    def profile(self, speeds):
        return loss.SpeedProfile("v", (0.0, 0.1, 0.2), tuple(speeds))

    def test_integrates_intermediate_deceleration_not_only_terminal_speed(self):
        reference = self.profile((10, 10, 10))
        slow_middle = self.profile((10, 0, 10))
        self.assertAlmostEqual(loss.distance_loss(reference, slow_middle), 1.0)
        self.assertAlmostEqual(loss.distance_loss(
            reference, slow_middle, loss_mode="terminal-held"), 0.0)

    def test_terminal_held_loss_uses_only_endpoint_on_horizon_scale(self):
        reference = self.profile((10, 10, 10))
        slower = self.profile((9, 9, 9))
        self.assertAlmostEqual(loss.distance_loss(
            reference, slower, loss_mode="terminal-held"), .2)
        with self.assertRaisesRegex(ValueError, "loss mode"):
            loss.distance_loss(reference, slower, loss_mode="unknown")
        decision = loss.time_equivalent_decision(
            {"v": reference}, {"v": slower}, {"v": reference}, {"v": 10},
            request_arrival_s=1, receiver_arrival_s=1,
            loss_mode="terminal-held")
        self.assertEqual(decision["loss_mode"], "terminal-held")

    def test_keeps_signed_speed_gain_visible(self):
        reference = self.profile((5, 5, 5))
        faster = self.profile((6, 6, 6))
        self.assertAlmostEqual(loss.distance_loss(reference, faster), -.2)

    def test_time_half_life_downweights_distant_loss(self):
        reference = self.profile((10, 10, 10))
        slower = self.profile((9, 9, 9))

        weighted = loss.distance_loss(
            reference, slower, time_half_life_s=.1)

        self.assertAlmostEqual(
            weighted, .1 * (2 ** -.5 + 2 ** -1.5))
        self.assertLess(weighted, loss.distance_loss(reference, slower))

    def test_time_half_life_must_be_positive(self):
        with self.assertRaises(ValueError):
            loss.distance_loss(
                self.profile((10, 10, 10)), self.profile((9, 9, 9)),
                time_half_life_s=0)

    def test_margin_uses_reject_minus_accept(self):
        reference = {"v": self.profile((10, 10, 10))}
        accept = {"v": self.profile((9, 9, 9))}
        reject = {"v": self.profile((8, 8, 8))}
        self.assertAlmostEqual(loss.decision_margin(reference, accept, reject)[
            "reject_minus_accept_m"], .2)

    def test_time_equivalent_formula_covers_arrival_loss_tradeoff_and_tie(self):
        reference = {"v": self.profile((10, 10, 10))}
        neutral = {"v": self.profile((10, 10, 10))}
        slow = {"v": self.profile((5, 5, 5))}
        arrival_only = loss.time_equivalent_decision(
            reference, neutral, neutral, {"v": 10},
            request_arrival_s=2, receiver_arrival_s=3)
        self.assertEqual(arrival_only["decision"], "accept")
        self.assertAlmostEqual(arrival_only["final_margin_s"], -1)

        loss_only = loss.time_equivalent_decision(
            reference, neutral, slow, {"v": 10},
            request_arrival_s=2, receiver_arrival_s=2)
        self.assertEqual(loss_only["decision"], "accept")
        tradeoff = loss.time_equivalent_decision(
            reference, slow, neutral, {"v": .1},
            request_arrival_s=1, receiver_arrival_s=2)
        self.assertEqual(tradeoff["decision"], "reject")
        tie = loss.time_equivalent_decision(
            reference, neutral, neutral, {"v": 10},
            request_arrival_s=2, receiver_arrival_s=2)
        self.assertEqual(tie["final_margin_s"], 0)
        self.assertEqual(tie["decision"], "accept")

    def test_request_unreachable_rejects_even_when_both_unreachable(self):
        reference = {"v": self.profile((10, 10, 10))}
        for receiver_arrival in (2, math.inf):
            result = loss.time_equivalent_decision(
                reference, reference, reference, {"v": 10},
                request_arrival_s=math.inf,
                receiver_arrival_s=receiver_arrival)
            self.assertEqual(result["decision"], "reject")
            self.assertFalse(result["request_arrival_reached"])
            self.assertEqual(result["decision_basis"], "unreachable_arrival")

    def test_receiver_unreachable_is_explicit_and_accepts(self):
        reference = {"v": self.profile((10, 10, 10))}
        result = loss.time_equivalent_decision(
            reference, reference, reference, {"v": 10},
            request_arrival_s=2, receiver_arrival_s=math.inf)

        self.assertEqual(result["decision"], "accept")
        self.assertEqual(result["arrival_status"], "receiver_unreached")
        self.assertTrue(result["request_arrival_reached"])
        self.assertFalse(result["receiver_arrival_reached"])

    def test_invalid_allowed_speed_is_unsupported(self):
        reference = {"v": self.profile((10, 10, 10))}
        for value in (0, math.nan):
            with self.assertRaises(ValueError):
                loss.time_equivalent_decision(
                    reference, reference, reference, {"v": value},
                    request_arrival_s=1, receiver_arrival_s=2)
        with self.assertRaises(ValueError):
            loss.time_equivalent_decision(
                reference, reference, reference, {},
                request_arrival_s=1, receiver_arrival_s=2)

    def test_same_distance_loss_depends_on_car_or_bus_allowed_speed(self):
        reference = {"v": self.profile((10, 10, 10))}
        slow = {"v": self.profile((5, 5, 5))}
        car = loss.time_equivalent_decision(
            reference, slow, reference, {"v": 10},
            request_arrival_s=1, receiver_arrival_s=1)
        bus = loss.time_equivalent_decision(
            reference, slow, reference, {"v": 5},
            request_arrival_s=1, receiver_arrival_s=1)
        self.assertAlmostEqual(
            bus["accept_time_equivalent_loss_s"],
            car["accept_time_equivalent_loss_s"] * 2)

    def test_shadow_does_not_mutate_live_paths_or_decision_state(self):
        def path(veh, kind, speeds):
            return NS(vehID=veh, type=kind, pathID=veh + "_path",
                      t=[0.0, 5.0, 10.0], s_d=speeds,
                      x=[0.0, 40.0, 80.0], y=[0.0, 0.0, 0.0],
                      allowed_speed_mps=10.0)
        sender_planned = path("a", "planned", [8, 8, 8])
        desired = path("a", "desired", [13, 13, 13])
        receiver_planned = path("b", "planned", [8, 8, 8])
        alternative = path("b", "alter", [8, 8, 8])
        receiver = NS(id="b", plannedPath=receiver_planned,
                      receivedPaths=[sender_planned], status="free")
        prediction.configure("shadow")
        before = (list(receiver_planned.s_d), list(desired.s_d), receiver.status)
        record = prediction.record_shadow(
            receiver, desired, alternative, 0.0, (40.0, 0.0))
        self.assertEqual(record["status"], "evaluated")
        self.assertEqual(before, (receiver_planned.s_d, desired.s_d, receiver.status))
        prediction.configure("off")

    def test_slow_zone_audit_requires_a_temporary_dip_and_recovery(self):
        context = {
            "enabled": True,
            "start_x_m": 172.2,
            "end_x_m": 174.2,
            "lane_center_y_m": -1.6,
            "lateral_tolerance_m": 1.0,
        }
        recovered = NS(
            t=[0.0, 5.0, 6.0, 10.0],
            x=[160.0, 173.0, 175.0, 210.0],
            y=[-1.6] * 4,
            s_d=[10.0, 8.0, 8.5, 10.0],
            slow_zone_reference_s_d=[10.0] * 4,
            slow_zone_context=context,
        )
        still_slow = NS(**{
            **recovered.__dict__,
            "s_d": [10.0, 8.0, 8.5, 9.0],
        })

        good = prediction._slow_zone_path_audit(recovered, 0.0)
        bad = prediction._slow_zone_path_audit(still_slow, 0.0)

        self.assertTrue(good["zone_entered_within_10s"])
        self.assertTrue(good["zone_exited_within_10s"])
        self.assertTrue(good["additional_deceleration_within_10s"])
        self.assertTrue(good["recovered_to_normal_speed_at_10s"])
        self.assertTrue(good["intended_temporary_slowdown"])
        self.assertIs(type(good["recovered_to_normal_speed_at_10s"]), bool)
        self.assertIs(type(good["intended_temporary_slowdown"]), bool)
        self.assertAlmostEqual(good["maximum_speed_reduction_mps"], 2.0)
        self.assertFalse(bad["recovered_to_normal_speed_at_10s"])
        self.assertFalse(bad["intended_temporary_slowdown"])

    def test_slow_zone_negotiation_summary_is_method_independent(self):
        context = {
            "enabled": True,
            "start_x_m": 172.2,
            "end_x_m": 174.2,
            "lane_center_y_m": -1.6,
            "lateral_tolerance_m": 1.0,
        }

        def path(veh, kind, name):
            return NS(
                vehID=veh, type=kind, pathID=name,
                t=[0.0, 5.0, 6.0, 10.0],
                x=[160.0, 173.0, 175.0, 210.0], y=[-1.6] * 4,
                s_d=[10.0, 8.0, 8.5, 10.0],
                slow_zone_reference_s_d=[10.0] * 4,
                slow_zone_context=context,
            )

        sender_planned = path("a", "planned", "a-planned")
        desired = path("a", "desired", "a-desired")
        receiver_planned = path("b", "planned", "b-planned")
        alternative = path("b", "alter", "b-alter")
        receiver = NS(
            id="b", plannedPath=receiver_planned,
            receivedPaths=[sender_planned])

        audit = prediction.slow_zone_negotiation_audit(
            receiver, desired, alternative, 0.0)

        self.assertTrue(audit["scenario_enabled"])
        self.assertTrue(audit["intended_profile_observed"])
        self.assertEqual(audit["intended_profile_path_count"], 4)
        self.assertEqual(
            {item["role"] for item in audit["paths"]},
            {"sender_desired", "sender_planned", "receiver_planned",
             "receiver_alternative"})

    def test_shadow_uses_newest_sender_planned_packet(self):
        def path(veh, kind, times, speeds, name):
            return NS(vehID=veh, type=kind, pathID=name, t=times, s_d=speeds,
                      x=[8 * time for time in times], y=[0.0 for _ in times],
                      allowed_speed_mps=10.0)
        old = path("a", "planned", [0.0, 5.0, 10.0], [1, 1, 1], "old")
        new = path("a", "planned", [1.0, 6.0, 11.0], [8, 8, 8], "new")
        desired = path("a", "desired", [1.0, 6.0, 11.0], [9, 9, 9], "desired")
        planned = path("b", "planned", [1.0, 6.0, 11.0], [8, 8, 8], "planned")
        alternative = path("b", "alter", [1.0, 6.0, 11.0], [6, 6, 6], "alter")
        receiver = NS(id="b", plannedPath=planned, receivedPaths=[old, new])
        prediction.configure("shadow")
        record = prediction.record_shadow(
            receiver, desired, alternative, 1.0, (40.0, 0.0))
        self.assertEqual(record["status"], "evaluated")
        prediction.configure("off")

    def test_shadow_propagates_lead_deceleration_to_a_follower(self):
        def path(veh, kind, x0, speeds):
            times = [0.0, 5.0, 10.0]
            return NS(vehID=veh, type=kind, pathID=veh + kind,
                      t=times, s_d=speeds,
                      x=[x0 + 8 * time for time in times], y=[0.0] * 3,
                      allowed_speed_mps=10.0)
        sender_planned = path("a", "planned", 20, [8, 8, 8])
        desired = path("a", "desired", 20, [8, 8, 8])
        receiver_planned = path("b", "planned", 10, [8, 8, 8])
        alternative = path("b", "alter", 10, [0, 0, 0])
        follower = path("c", "planned", 0, [8, 8, 8])
        receiver = NS(id="b", plannedPath=receiver_planned,
                      receivedPaths=[sender_planned, follower])
        result = prediction.evaluate(
            receiver, desired, alternative, 0.0, (40.0, 0.0))
        self.assertEqual(result["follower_count"], 1)
        self.assertIn("c", result["vehicle_ids"])
        self.assertEqual(result["replan_interval_s"], 1.0)
        self.assertEqual(result["follower_replans"], 10)
        self.assertEqual(result["loss_vehicle_ids"], ["c"])
        self.assertEqual(result["excluded_loss_vehicle_ids"], ["a", "b"])
        self.assertEqual(set(result["vehicle_loss_details"]), {"c"})

    def test_negotiating_actors_are_excluded_from_loss_but_follower_is_included(self):
        def path(veh, kind, x0, speeds):
            times = [0.0, 5.0, 10.0]
            return NS(vehID=veh, type=kind, pathID=veh + kind,
                      t=times, s_d=speeds,
                      x=[x0 + 8 * time for time in times], y=[0.0] * 3,
                      yaw=[0.0] * 3, allowed_speed_mps=10.0)

        sender_planned = path("a", "planned", 20, [8, 8, 8])
        desired = path("a", "desired", 20, [0, 0, 0])
        receiver_planned = path("b", "planned", 100, [8, 8, 8])
        alternative = path("b", "alter", 100, [0, 0, 0])
        follower = path("c", "planned", 0, [8, 8, 8])
        receiver = NS(id="b", plannedPath=receiver_planned,
                      receivedPaths=[sender_planned, follower])

        result = prediction.evaluate(
            receiver, desired, alternative, 0.0, (40.0, 0.0))

        self.assertEqual(result["loss_vehicle_ids"], ["c"])
        self.assertEqual(result["excluded_loss_vehicle_ids"], ["a", "b"])
        self.assertEqual(set(result["vehicle_loss_details"]), {"c"})
        self.assertNotEqual(result["accept_time_equivalent_loss_s"], 0.0)

    def test_counterfactuals_compare_union_of_different_follower_sets(self):
        def path(veh, kind, lane, y, lane_position, speeds):
            times = [0.0, 5.0, 10.0]
            return NS(
                vehID=veh, type=kind, pathID=veh + kind + lane,
                t=times, s_d=speeds,
                x=[20.0 + 8 * time for time in times], y=[y] * 3,
                yaw=[0.0] * 3, lane_id=lane,
                lane_position=lane_position, allowed_speed_mps=10.0)

        sender_planned = path(
            "a", "planned", "main_0", 0.0, 20.0, [8, 8, 8])
        desired = path(
            "a", "desired", "detour_0", 10.0, 20.0, [8, 8, 8])
        receiver_planned = path(
            "b", "planned", "receiver_0", 100.0, 20.0, [8, 8, 8])
        alternative = path(
            "b", "alter", "receiver_alt_0", 110.0, 20.0, [8, 8, 8])
        reject_only = path(
            "c", "planned", "main_0", 0.0, 0.0, [8, 8, 8])
        accept_only = path(
            "d", "planned", "detour_0", 10.0, 0.0, [8, 8, 8])
        receiver = NS(
            id="b", plannedPath=receiver_planned,
            receivedPaths=[sender_planned, reject_only, accept_only])

        result = prediction.evaluate(
            receiver, desired, alternative, 0.0, (60.0, 0.0))

        self.assertEqual(result["accept_follower_ids"], ["d"])
        self.assertEqual(result["reject_follower_ids"], ["c"])
        self.assertEqual(result["union_follower_ids"], ["c", "d"])
        self.assertEqual(result["vehicle_ids"], ["a", "b", "c", "d"])
        self.assertEqual(result["follower_count"], 2)

    def test_stationary_path_uses_mcm_yaw_for_same_lane_follower(self):
        def path(veh, x, lane):
            return NS(vehID=veh, type="planned", pathID=veh + "path",
                      t=[0.0, 5.0, 10.0], s_d=[0.0, 0.0, 0.0],
                      x=[x, x, x], y=[0.0, 0.0, 0.0],
                      yaw=[0.0, 0.0, 0.0], lane_id=lane)
        leader = path("a", 10.0, "left_0")
        follower = path("b", 0.0, "left_0")

        found = prediction._followers(
            "a", leader, {"b": follower}, 0.0, {"a"})

        self.assertEqual([entry[0] for entry in found], ["b"])

    def test_adjacent_parallel_lane_is_not_a_follower(self):
        def path(veh, x, lane, y):
            return NS(vehID=veh, type="planned", pathID=veh + "path",
                      t=[0.0, 5.0, 10.0], s_d=[8.0, 8.0, 8.0],
                      x=[x, x + 40.0, x + 80.0], y=[y, y, y],
                      yaw=[0.0, 0.0, 0.0], lane_id=lane)
        leader = path("a", 10.0, "main_0", 0.0)
        adjacent = path("b", 0.0, "main_1", 3.2)

        self.assertEqual(prediction._followers(
            "a", leader, {"b": adjacent}, 0.0, {"a"}), [])

    def test_curved_same_lane_uses_lane_progress_not_tangent_projection(self):
        leader = NS(vehID="a", type="planned", pathID="apath",
                    t=[0.0, 5.0, 10.0], s_d=[5.0, 5.0, 5.0],
                    x=[10.0, 10.0, 10.0], y=[0.0, 25.0, 50.0],
                    yaw=[math.pi / 2] * 3, lane_id=":turn_0",
                    lane_position=20.0)
        follower = NS(vehID="b", type="planned", pathID="bpath",
                      t=[0.0, 5.0, 10.0], s_d=[5.0, 5.0, 5.0],
                      x=[0.0, 10.0, 10.0], y=[0.0, 15.0, 40.0],
                      yaw=[0.0, math.pi / 2, math.pi / 2],
                      lane_id=":turn_0", lane_position=10.0)

        found = prediction._followers(
            "a", leader, {"b": follower}, 0.0, {"a"})

        self.assertEqual([entry[0] for entry in found], ["b"])

    def test_different_lanes_that_share_downstream_path_are_merge_followers(self):
        leader = NS(vehID="a", type="planned", pathID="apath",
                    t=[0.0, 5.0, 10.0], s_d=[8.0, 8.0, 8.0],
                    x=[0.0, 40.0, 80.0], y=[0.0, 0.0, 0.0],
                    yaw=[0.0, 0.0, 0.0], lane_id="main_0")
        merging = NS(vehID="b", type="planned", pathID="bpath",
                     t=[0.0, 5.0, 10.0], s_d=[8.0, 8.0, 8.0],
                     x=[-10.0, 40.0, 80.0], y=[3.2, 0.0, 0.0],
                     yaw=[0.0, 0.0, 0.0], lane_id="ramp_0")

        found = prediction._followers(
            "a", leader, {"b": merging}, 0.0, {"a"})

        self.assertEqual([entry[0] for entry in found], ["b"])

    def test_perpendicular_crossing_path_is_not_a_merge_follower(self):
        leader = NS(vehID="a", type="planned", pathID="apath",
                    t=[0.0, 5.0, 10.0], s_d=[8.0, 8.0, 8.0],
                    x=[0.0, 40.0, 80.0], y=[0.0, 0.0, 0.0],
                    yaw=[0.0, 0.0, 0.0], lane_id="eastbound_0")
        crossing = NS(vehID="b", type="planned", pathID="bpath",
                      t=[0.0, 5.0, 10.0], s_d=[8.0, 8.0, 8.0],
                      x=[40.0, 40.0, 40.0], y=[-40.0, 0.0, 40.0],
                      yaw=[math.pi / 2] * 3, lane_id="northbound_0")

        self.assertEqual(prediction._followers(
            "a", leader, {"b": crossing}, 0.0, {"a"}), [])

    def test_prediction_records_selected_time_half_life(self):
        def path(veh, kind, x0, speeds):
            times = [0.0, 5.0, 10.0]
            return NS(vehID=veh, type=kind, pathID=veh + kind,
                      t=times, s_d=speeds,
                      x=[x0 + 8 * time for time in times], y=[0.0] * 3,
                      allowed_speed_mps=10.0)
        receiver = NS(
            id="b", plannedPath=path("b", "planned", 10, [8, 8, 8]),
            receivedPaths=[path("a", "planned", 20, [8, 8, 8])])

        with patch.object(prediction, "TIME_HALF_LIFE_S", 3.0):
            result = prediction.evaluate(
                receiver, path("a", "desired", 20, [10, 10, 10]),
                path("b", "alter", 10, [6, 6, 6]), 0.0, (60.0, 0.0))

        self.assertEqual(result["time_weighting"], "exponential-half-life")
        self.assertEqual(result["time_half_life_s"], 3.0)

    def test_active_decision_is_available_only_in_active_mode(self):
        def path(veh, kind, speeds):
            return NS(vehID=veh, type=kind, pathID=veh + kind,
                      t=[0.0, 5.0, 10.0], s_d=speeds,
                      x=[0.0, 40.0, 80.0], y=[0.0, 0.0, 0.0],
                      allowed_speed_mps=10.0)
        sender = path("a", "planned", [8, 8, 8])
        desired = path("a", "desired", [13, 13, 13])
        planned = path("b", "planned", [8, 8, 8])
        alternative = path("b", "alter", [8, 8, 8])
        receiver = NS(id="b", plannedPath=planned, receivedPaths=[sender])
        prediction.configure("active")
        self.assertTrue(prediction.active_decision(
            receiver, desired, alternative, 0.0, (40.0, 0.0)))
        prediction.configure("off")
        self.assertIsNone(prediction.active_decision(
            receiver, desired, alternative, 0.0, (40.0, 0.0)))

    def test_active_decision_locks_only_the_same_desired_path_for_one_second(self):
        def path(veh, kind, name, speeds):
            return NS(vehID=veh, type=kind, pathID=name,
                      t=[0.0, 5.0, 10.0], s_d=speeds,
                      x=[0.0, 40.0, 80.0], y=[0.0, 0.0, 0.0],
                      allowed_speed_mps=10.0)
        sender = path("a", "planned", "a_planned", [8, 8, 8])
        desired = path("a", "desired", "a_desired_1", [13, 13, 13])
        planned = path("b", "planned", "b_planned", [8, 8, 8])
        alternative = path("b", "alter", "b_alter", [8, 8, 8])
        receiver = NS(id="b", plannedPath=planned, receivedPaths=[sender])
        prediction.configure("active")
        prediction.active_decision(
            receiver, desired, alternative, 0.0, (40.0, 0.0))
        self.assertTrue(prediction.active_decision_is_locked(receiver, desired, 0.9))
        self.assertFalse(prediction.active_decision_is_locked(receiver, desired, 1.0))
        newer_desired = path("a", "desired", "a_desired_2", [13, 13, 13])
        self.assertFalse(prediction.active_decision_is_locked(receiver, newer_desired, 0.1))
        prediction.configure("off")


if __name__ == "__main__":
    unittest.main()

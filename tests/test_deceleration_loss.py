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

    def test_keeps_signed_speed_gain_visible(self):
        reference = self.profile((5, 5, 5))
        faster = self.profile((6, 6, 6))
        self.assertAlmostEqual(loss.distance_loss(reference, faster), -.2)

    def test_margin_uses_reject_minus_accept(self):
        reference = {"v": self.profile((10, 10, 10))}
        accept = {"v": self.profile((9, 9, 9))}
        reject = {"v": self.profile((8, 8, 8))}
        self.assertAlmostEqual(loss.decision_margin(reference, accept, reject)[
            "reject_minus_accept_m"], .2)

    def test_shadow_does_not_mutate_live_paths_or_decision_state(self):
        def path(veh, kind, speeds):
            return NS(vehID=veh, type=kind, pathID=veh + "_path",
                      t=[0.0, 5.0, 10.0], s_d=speeds,
                      x=[0.0, 40.0, 80.0], y=[0.0, 0.0, 0.0])
        sender_planned = path("a", "planned", [8, 8, 8])
        desired = path("a", "desired", [13, 13, 13])
        receiver_planned = path("b", "planned", [8, 8, 8])
        alternative = path("b", "alter", [8, 8, 8])
        receiver = NS(id="b", plannedPath=receiver_planned,
                      receivedPaths=[sender_planned], status="free")
        prediction.configure("shadow")
        before = (list(receiver_planned.s_d), list(desired.s_d), receiver.status)
        record = prediction.record_shadow(receiver, desired, alternative, 0.0)
        self.assertEqual(record["status"], "evaluated")
        self.assertEqual(before, (receiver_planned.s_d, desired.s_d, receiver.status))
        prediction.configure("off")

    def test_shadow_uses_newest_sender_planned_packet(self):
        def path(veh, kind, times, speeds, name):
            return NS(vehID=veh, type=kind, pathID=name, t=times, s_d=speeds,
                      x=[8 * time for time in times], y=[0.0 for _ in times])
        old = path("a", "planned", [0.0, 5.0, 10.0], [1, 1, 1], "old")
        new = path("a", "planned", [1.0, 6.0, 11.0], [8, 8, 8], "new")
        desired = path("a", "desired", [1.0, 6.0, 11.0], [9, 9, 9], "desired")
        planned = path("b", "planned", [1.0, 6.0, 11.0], [8, 8, 8], "planned")
        alternative = path("b", "alter", [1.0, 6.0, 11.0], [6, 6, 6], "alter")
        receiver = NS(id="b", plannedPath=planned, receivedPaths=[old, new])
        prediction.configure("shadow")
        record = prediction.record_shadow(receiver, desired, alternative, 1.0)
        self.assertEqual(record["status"], "evaluated")
        prediction.configure("off")

    def test_shadow_propagates_lead_deceleration_to_a_follower(self):
        def path(veh, kind, x0, speeds):
            times = [0.0, 5.0, 10.0]
            return NS(vehID=veh, type=kind, pathID=veh + kind,
                      t=times, s_d=speeds,
                      x=[x0 + 8 * time for time in times], y=[0.0] * 3)
        sender_planned = path("a", "planned", 20, [8, 8, 8])
        desired = path("a", "desired", 20, [8, 8, 8])
        receiver_planned = path("b", "planned", 10, [8, 8, 8])
        alternative = path("b", "alter", 10, [0, 0, 0])
        follower = path("c", "planned", 0, [8, 8, 8])
        receiver = NS(id="b", plannedPath=receiver_planned,
                      receivedPaths=[sender_planned, follower])
        result = prediction.evaluate(receiver, desired, alternative, 0.0)
        self.assertEqual(result["follower_count"], 1)
        self.assertIn("c", result["vehicle_ids"])
        self.assertEqual(result["replan_interval_s"], 1.0)
        self.assertEqual(result["follower_replans"], 10)

    def test_active_decision_is_available_only_in_active_mode(self):
        def path(veh, kind, speeds):
            return NS(vehID=veh, type=kind, pathID=veh + kind,
                      t=[0.0, 5.0, 10.0], s_d=speeds,
                      x=[0.0, 40.0, 80.0], y=[0.0, 0.0, 0.0])
        sender = path("a", "planned", [8, 8, 8])
        desired = path("a", "desired", [13, 13, 13])
        planned = path("b", "planned", [8, 8, 8])
        alternative = path("b", "alter", [8, 8, 8])
        receiver = NS(id="b", plannedPath=planned, receivedPaths=[sender])
        prediction.configure("active")
        self.assertTrue(prediction.active_decision(receiver, desired, alternative, 0.0))
        prediction.configure("off")
        self.assertIsNone(prediction.active_decision(receiver, desired, alternative, 0.0))

    def test_active_decision_locks_only_the_same_desired_path_for_one_second(self):
        def path(veh, kind, name, speeds):
            return NS(vehID=veh, type=kind, pathID=name,
                      t=[0.0, 5.0, 10.0], s_d=speeds,
                      x=[0.0, 40.0, 80.0], y=[0.0, 0.0, 0.0])
        sender = path("a", "planned", "a_planned", [8, 8, 8])
        desired = path("a", "desired", "a_desired_1", [13, 13, 13])
        planned = path("b", "planned", "b_planned", [8, 8, 8])
        alternative = path("b", "alter", "b_alter", [8, 8, 8])
        receiver = NS(id="b", plannedPath=planned, receivedPaths=[sender])
        prediction.configure("active")
        prediction.active_decision(receiver, desired, alternative, 0.0)
        self.assertTrue(prediction.active_decision_is_locked(receiver, desired, 0.9))
        self.assertFalse(prediction.active_decision_is_locked(receiver, desired, 1.0))
        newer_desired = path("a", "desired", "a_desired_2", [13, 13, 13])
        self.assertFalse(prediction.active_decision_is_locked(receiver, newer_desired, 0.1))
        prediction.configure("off")


if __name__ == "__main__":
    unittest.main()

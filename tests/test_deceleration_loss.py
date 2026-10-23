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
                      t=[0.0, 5.0, 10.0], s_d=speeds)
        sender_planned = path("a", "planned", [8, 8, 8])
        desired = path("a", "desired", [9, 9, 9])
        receiver_planned = path("b", "planned", [8, 8, 8])
        alternative = path("b", "alter", [6, 6, 6])
        receiver = NS(id="b", plannedPath=receiver_planned,
                      receivedPaths=[sender_planned], status="free")
        prediction.configure("shadow")
        before = (list(receiver_planned.s_d), list(desired.s_d), receiver.status)
        record = prediction.record_shadow(receiver, desired, alternative, 0.0)
        self.assertEqual(record["status"], "direct-cars-only")
        self.assertEqual(before, (receiver_planned.s_d, desired.s_d, receiver.status))
        prediction.configure("off")

    def test_shadow_uses_newest_sender_planned_packet(self):
        def path(veh, kind, times, speeds, name):
            return NS(vehID=veh, type=kind, pathID=name, t=times, s_d=speeds)
        old = path("a", "planned", [0.0, 5.0, 10.0], [1, 1, 1], "old")
        new = path("a", "planned", [1.0, 6.0, 11.0], [8, 8, 8], "new")
        desired = path("a", "desired", [1.0, 6.0, 11.0], [9, 9, 9], "desired")
        planned = path("b", "planned", [1.0, 6.0, 11.0], [8, 8, 8], "planned")
        alternative = path("b", "alter", [1.0, 6.0, 11.0], [6, 6, 6], "alter")
        receiver = NS(id="b", plannedPath=planned, receivedPaths=[old, new])
        prediction.configure("shadow")
        record = prediction.record_shadow(receiver, desired, alternative, 1.0)
        self.assertEqual(record["status"], "direct-cars-only")
        prediction.configure("off")


if __name__ == "__main__":
    unittest.main()

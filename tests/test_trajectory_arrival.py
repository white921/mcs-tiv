import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "func"))
import trajectory_arrival as arrival


def path(x, y, times=None):
    times = times or [index / 10 for index in range(len(x))]
    return NS(t=times, x=x, y=y)


class TrajectoryArrivalTests(unittest.TestCase):
    def test_both_conflicting_trajectories_enter_same_region_within_horizon(self):
        times = [index / 10 for index in range(101)]
        request = path([10 * value for value in times], [0.0] * 101, times)
        receiver = path([10 + 10 * value for value in times], [1.0] * 101, times)
        collision = {
            "collide_x": 60.0,
            "collide_y": 1.0,
            "duration": 5.0,
        }

        region = arrival.conflict_region(request, receiver, collision, 0.0)

        self.assertAlmostEqual(arrival.arrival_delay(request, region, 0.0), 4.0)
        self.assertAlmostEqual(arrival.arrival_delay(receiver, region, 0.0), 3.0)
        self.assertEqual(region["horizon_s"], 10.0)
        self.assertTrue(math.isfinite(arrival.arrival_delay(request, region, 0.0)))
        self.assertTrue(math.isfinite(arrival.arrival_delay(receiver, region, 0.0)))

    def test_vertical_conflict_region_uses_receiver_heading(self):
        times = [index / 10 for index in range(101)]
        request = path([1.0] * 101, [10 * value for value in times], times)
        receiver = path([0.0] * 101, [10 + 10 * value for value in times], times)
        collision = {
            "collide_x": 0.0,
            "collide_y": 60.0,
            "duration": 5.0,
        }

        region = arrival.conflict_region(request, receiver, collision, 0.0)

        self.assertAlmostEqual(region["heading_rad"], math.pi / 2)
        self.assertAlmostEqual(arrival.arrival_delay(request, region, 0.0), 4.0)
        self.assertAlmostEqual(arrival.arrival_delay(receiver, region, 0.0), 3.0)

    def test_region_contains_both_centres_when_safety_areas_overlap_at_a_distance(self):
        times = [index / 10 for index in range(101)]
        request = path([8 * value for value in times], [0.0] * 101, times)
        receiver = path([20 + 8 * value for value in times], [1.0] * 101, times)
        collision = {
            "collide_x": 60.0,
            "collide_y": 1.0,
            "duration": 5.0,
        }

        region = arrival.conflict_region(request, receiver, collision, 0.0)

        self.assertEqual(region["center_x_m"], 50.0)
        self.assertEqual(region["center_y_m"], 0.5)
        self.assertTrue(math.isfinite(
            arrival.arrival_delay(request, region, 0.0)))
        self.assertTrue(math.isfinite(
            arrival.arrival_delay(receiver, region, 0.0)))

    def test_missing_region_entry_is_an_inconsistent_event(self):
        stopped = path([0.0] * 101, [0.0] * 101)
        region = {
            "schema_version": 1,
            "center_x_m": 100.0,
            "center_y_m": 0.0,
            "heading_rad": 0.0,
            "longitudinal_radius_m": 5.0,
            "lateral_radius_m": 1.8,
            "horizon_s": 10.0,
        }

        with self.assertRaisesRegex(ValueError, "does not enter"):
            arrival.arrival_delay(stopped, region, 0.0)

    def test_region_schema_and_horizon_are_fixed(self):
        moving = path(
            [index / 10 for index in range(101)], [0.0] * 101)
        valid = {
            "schema_version": 1,
            "center_x_m": 1.0,
            "center_y_m": 0.0,
            "heading_rad": 0.0,
            "longitudinal_radius_m": 1.0,
            "lateral_radius_m": 1.0,
            "horizon_s": 10.0,
        }
        with self.assertRaisesRegex(ValueError, "schema"):
            arrival.arrival_delay(
                moving, {**valid, "schema_version": 2}, 0.0)
        with self.assertRaisesRegex(ValueError, "10 seconds"):
            arrival.arrival_delay(
                moving, {**valid, "horizon_s": 20.0}, 0.0)

    def test_conflict_outside_prediction_horizon_is_rejected(self):
        stationary = path([0.0] * 101, [0.0] * 101)
        with self.assertRaisesRegex(ValueError, "outside"):
            arrival.conflict_region(
                stationary,
                stationary,
                {"collide_x": 0.0, "collide_y": 0.0, "duration": 10.1},
                0.0,
            )


if __name__ == "__main__":
    unittest.main()

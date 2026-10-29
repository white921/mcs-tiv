from contextlib import redirect_stdout
import importlib.util
import io
import math
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "PathPlanning" / "FrenetOptimalTrajectory" / "eval3_slow_zone.py")
SPEC = importlib.util.spec_from_file_location("eval3_slow_zone", MODULE_PATH)
SLOW_ZONE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SLOW_ZONE)


def straight_path(y=-1.6, speed=13.89, samples=101):
    dt = 0.1
    xs = [140.0 + speed * dt * index for index in range(samples)]
    return SimpleNamespace(
        t=[dt * index for index in range(samples)],
        x=xs,
        y=[y] * samples,
        s=list(xs),
        d=[0.0] * samples,
        d_d=[0.0] * samples,
        d_dd=[0.0] * samples,
        d_ddd=[0.0] * samples,
        s_d=[speed] * samples,
        s_dd=[0.0] * samples,
        s_ddd=[0.0] * samples,
        yaw=[0.0] * samples,
        ds=[speed * dt] * samples,
        c=[0.0] * samples,
    )


class Eval3SlowZoneTests(unittest.TestCase):
    def test_environment_switch_rejects_ambiguous_values(self):
        self.assertFalse(SLOW_ZONE.enabled_from_environment({}))
        self.assertTrue(SLOW_ZONE.enabled_from_environment({
            SLOW_ZONE.ENVIRONMENT_SWITCH: "1",
        }))
        with self.assertRaises(ValueError):
            SLOW_ZONE.enabled_from_environment({
                SLOW_ZONE.ENVIRONMENT_SWITCH: "yes",
            })

    def test_target_path_slows_and_recovers_within_ten_seconds(self):
        path = straight_path()

        SLOW_ZONE.apply_to_path(
            path, max_speed=13.89, max_accel=3.0, max_decel=-5.0)

        zone_speeds = [
            speed for x, y, speed in zip(path.x, path.y, path.s_d)
            if (SLOW_ZONE.ZONE["start_x_m"] <= x <= SLOW_ZONE.ZONE["end_x_m"] and
                abs(y - SLOW_ZONE.ZONE["lane_center_y_m"]) < 0.1)
        ]
        self.assertTrue(zone_speeds)
        self.assertLessEqual(max(zone_speeds), SLOW_ZONE.ZONE["speed_limit_mps"] + 0.06)
        self.assertLess(min(path.s_d), 8.7)
        self.assertGreater(path.s_d[-1], 13.0)
        self.assertTrue(all(right >= left for left, right in zip(path.x, path.x[1:])))
        self.assertEqual(len(path.t), len(path.x))
        self.assertEqual(len(path.t), len(path.s_d))

        accelerations = [
            (right - left) / 0.1
            for left, right in zip(path.s_d, path.s_d[1:])
        ]
        self.assertLessEqual(max(accelerations), 3.0 + 1e-9)
        self.assertGreaterEqual(min(accelerations), -5.0 - 1e-9)

    def test_bus_motion_limits_still_recover_within_ten_seconds(self):
        path = straight_path(speed=11.11)

        SLOW_ZONE.apply_to_path(
            path, max_speed=11.11, max_accel=1.0, max_decel=-3.0)

        self.assertLess(min(path.s_d), 8.7)
        self.assertGreater(path.s_d[-1], 10.9)

    def test_real_turn_planner_exposes_dip_and_recovery_for_car_and_bus(self):
        import numpy as np

        planner_directory = ROOT / "PathPlanning" / "FrenetOptimalTrajectory"
        sys.path.insert(0, str(planner_directory))
        try:
            import frenet_three_junction as planner

            previous = os.environ.get(SLOW_ZONE.ENVIRONMENT_SWITCH)
            os.environ[SLOW_ZONE.ENVIRONMENT_SWITCH] = "1"
            try:
                for vehicle_type, max_speed, max_accel, max_decel in (
                    ("car", 13.89, 3.0, -5.0),
                    ("bus", 11.11, 1.0, -3.0),
                ):
                    with redirect_stdout(io.StringIO()):
                        paths = planner.generate_frenet_frame(
                            objects=np.empty((0, 2)),
                            c_s=100.0,
                            c_s_d=10.0,
                            c_s_dd=0.0,
                            c_d=0.0,
                            mode="turn",
                            route="BR",
                            target_pos=141.8,
                            simTime=0.0,
                            vehInstance=SimpleNamespace(id=vehicle_type),
                            vehicle_max_speed=max_speed,
                            vehicle_max_accel=max_accel,
                            vehicle_max_decel=max_decel,
                        )
                    self.assertEqual(len(paths), 1)
                    path = paths[0]
                    zone_speeds = [
                        speed for x, y, speed in zip(path.x, path.y, path.s_d)
                        if (SLOW_ZONE.ZONE["start_x_m"] <= x <=
                            SLOW_ZONE.ZONE["end_x_m"] and
                            abs(y - SLOW_ZONE.ZONE["lane_center_y_m"]) <= 1.0)
                    ]
                    speed_at_ten = next(
                        speed for time, speed in zip(path.t, path.s_d)
                        if abs(time - 10.0) < 1e-9)
                    self.assertTrue(zone_speeds)
                    self.assertLessEqual(
                        max(zone_speeds), SLOW_ZONE.ZONE["speed_limit_mps"] + 0.01)
                    self.assertAlmostEqual(speed_at_ten, max_speed, places=2)
            finally:
                if previous is None:
                    os.environ.pop(SLOW_ZONE.ENVIRONMENT_SWITCH, None)
                else:
                    os.environ[SLOW_ZONE.ENVIRONMENT_SWITCH] = previous
        finally:
            sys.path.remove(str(planner_directory))

    def test_other_outgoing_lanes_are_unchanged(self):
        path = straight_path(y=1.6)
        original_x = list(path.x)
        original_speed = list(path.s_d)

        SLOW_ZONE.apply_to_path(
            path, max_speed=13.89, max_accel=3.0, max_decel=-5.0)

        self.assertEqual(path.x, original_x)
        self.assertEqual(path.s_d, original_speed)

    def test_disabled_scenario_leaves_target_path_unchanged(self):
        path = straight_path()
        original_x = list(path.x)

        SLOW_ZONE.apply_to_paths(
            [path], max_speed=13.89, max_accel=3.0, max_decel=-5.0,
            enabled=False)

        self.assertEqual(path.x, original_x)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fallback_ablation",
    ROOT / "scripts" / "run_intersection_lane_heading_fallback_ablation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IntersectionLaneHeadingFallbackAblationTest(unittest.TestCase):
    def summary(self, stationary=18, lane_positions=19, unknown_lanes=1):
        return {
            "analysis": "topology-heading-attribution-diagnostic",
            "validated_run_count": 15,
            "physical_collision_count": 0,
            "conditions": {
                "eval3:500-500-500": {
                    "retained_with_details": 10,
                    "stationary_without_yaw": stationary // 2,
                    "lane_position_present": lane_positions // 2,
                    "lane_id": {"unknown": unknown_lanes},
                },
                "eval5:300-300-300-300": {
                    "retained_with_details": 10,
                    "stationary_without_yaw": stationary - stationary // 2,
                    "lane_position_present": lane_positions - lane_positions // 2,
                    "lane_id": {},
                },
            },
        }

    def write_summary(self, directory, value):
        path = Path(directory) / "summary.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_gate_accepts_dominant_lane_aware_stationary_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            report = MODULE.gate_report(self.write_summary(
                directory, self.summary()))
        self.assertTrue(report["eligible"])
        self.assertEqual(report["retained_with_details"], 20)
        self.assertGreaterEqual(report["stationary_without_yaw_fraction"], 0.8)

    def test_gate_rejects_weak_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_summary(directory, self.summary(stationary=12))
            with self.assertRaisesRegex(RuntimeError, "not dominant"):
                MODULE.gate_report(path)

    def test_all_commands_use_fallback_and_fifteen_slots(self):
        self.assertEqual(sum(len(spec["seeds"]) for spec in MODULE.SPECS), 15)
        for spec in MODULE.SPECS:
            command = MODULE.command(
                Path("/output"), Path("/sumo"), "/python", spec)
            self.assertIn(
                "--deceleration-lane-metadata-heading-fallback", command)
            self.assertEqual(command[command.index("--workers") + 1], "5")


if __name__ == "__main__":
    unittest.main()

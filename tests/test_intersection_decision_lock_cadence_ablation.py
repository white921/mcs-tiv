import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "decision_lock_ablation",
    ROOT / "scripts" / "run_intersection_decision_lock_cadence_ablation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IntersectionDecisionLockCadenceAblationTest(unittest.TestCase):
    def test_uses_all_fifteen_slots_in_intersection_cohorts(self):
        self.assertEqual(sum(len(spec["seeds"]) for spec in MODULE.SPECS), 15)
        self.assertEqual([spec["case"] for spec in MODULE.SPECS], [
            "eval3", "eval5", "eval5",
        ])

    def test_command_changes_only_heading_and_decision_lock_ablation_flags(self):
        for spec in MODULE.SPECS:
            command = MODULE.command(
                Path("/artifact"), Path("/sumo"), "/python", spec)
            self.assertIn("--deceleration-active", command)
            self.assertIn(
                "--deceleration-lane-metadata-heading-fallback", command)
            self.assertEqual(command[command.index(
                "--deceleration-convex-lambda") + 1], "0.95")
            self.assertEqual(command[command.index(
                "--deceleration-decision-lock-seconds") + 1], "0.1")
            self.assertEqual(command[command.index("--workers") + 1], "5")
            self.assertIn("--fixed-input-override", command)


if __name__ == "__main__":
    unittest.main()

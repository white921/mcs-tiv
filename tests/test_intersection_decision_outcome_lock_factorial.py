import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "outcome_lock_factorial",
    ROOT / "scripts" / "run_intersection_decision_outcome_lock_factorial.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IntersectionDecisionOutcomeLockFactorialTest(unittest.TestCase):
    def test_two_outcome_specific_arms_cover_the_missing_factorial_cells(self):
        self.assertEqual([
            (arm["accept_lock_s"], arm["reject_lock_s"])
            for arm in MODULE.ARMS
        ], [(0.1, 1.0), (1.0, 0.1)])

    def test_each_wave_uses_all_fifteen_slots(self):
        self.assertEqual(sum(len(spec["seeds"]) for spec in MODULE.SPECS), 15)
        self.assertEqual([spec["case"] for spec in MODULE.SPECS], [
            "eval3", "eval5", "eval5",
        ])

    def test_command_records_both_outcome_specific_locks(self):
        for arm in MODULE.ARMS:
            for spec in MODULE.SPECS:
                command = MODULE.command(
                    Path("/artifact"), Path("/sumo"), "/python", arm, spec)
                self.assertEqual(command[command.index(
                    "--deceleration-decision-lock-accept-seconds") + 1],
                    str(arm["accept_lock_s"]))
                self.assertEqual(command[command.index(
                    "--deceleration-decision-lock-reject-seconds") + 1],
                    str(arm["reject_lock_s"]))
                self.assertEqual(command[command.index("--workers") + 1], "5")
                self.assertIn("--fixed-input-override", command)


if __name__ == "__main__":
    unittest.main()

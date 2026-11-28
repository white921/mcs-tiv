import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "heading_diagnostic",
    ROOT / "scripts" / "run_topology_heading_attribution_diagnostic.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TopologyHeadingAttributionDiagnosticTest(unittest.TestCase):
    def test_uses_all_fifteen_slots_in_three_fixed_cohorts(self):
        self.assertEqual(sum(len(spec["seeds"]) for spec in MODULE.SPECS), 15)
        self.assertEqual([spec["case"] for spec in MODULE.SPECS], [
            "eval3", "eval5", "eval7"
        ])

    def test_commands_keep_behavior_fixed_and_enable_diagnostics(self):
        root = Path("/artifact")
        sumo = Path("/sumo")
        for spec in MODULE.SPECS:
            command = MODULE.command(root, sumo, "/python", spec)
            self.assertIn("--deceleration-active", command)
            self.assertEqual(command[command.index(
                "--deceleration-convex-lambda") + 1], "0.95")
            self.assertIn("--diagnostic-traces", command)
            self.assertEqual(command[command.index("--workers") + 1], "5")
            self.assertIn("--fixed-input-override", command)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "accept_lock_sweep",
    ROOT / "scripts" / "run_intersection_accept_lock_sweep.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IntersectionAcceptLockSweepTest(unittest.TestCase):
    def test_three_intermediate_waves_fill_fifteen_slots(self):
        self.assertEqual(MODULE.ACCEPT_LOCKS_S, (0.3, 0.5, 0.7))
        self.assertEqual(sum(len(spec["seeds"]) for spec in MODULE.SPECS), 15)
        self.assertEqual(MODULE.REJECT_LOCK_S, 1.0)
        for value in MODULE.ACCEPT_LOCKS_S:
            commands = [
                MODULE.command(
                    Path("/output"), Path("/sumo"), "python", value, spec)
                for spec in MODULE.SPECS
            ]
            self.assertTrue(all(
                command[command.index(
                    "--deceleration-decision-lock-accept-seconds") + 1]
                == str(value)
                for command in commands
            ))
            self.assertTrue(all(
                command[command.index(
                    "--deceleration-decision-lock-reject-seconds") + 1]
                == "1.0"
                for command in commands
            ))

    def test_gate_requires_fully_validated_degeneracy(self):
        value = {
            "analysis": "intersection-decision-outcome-lock-degeneracy",
            "physical_collision_count": 0,
            "validated_run_count": 45,
            "validated_new_run_count": 15,
            "reject_lock_degeneracy": {
                "supported": True,
                "exact_record_matches": 15,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            result = MODULE.degeneracy_gate(path)
            self.assertTrue(result["eligible"])
            value["reject_lock_degeneracy"]["exact_record_matches"] = 14
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "cover all 15"):
                MODULE.degeneracy_gate(path)


if __name__ == "__main__":
    unittest.main()

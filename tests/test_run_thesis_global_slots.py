import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_thesis_global_slots.py"
SPEC = importlib.util.spec_from_file_location("run_thesis_global_slots", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class GlobalSlotTests(unittest.TestCase):
    def test_external_runs_reduce_capacity(self):
        self.assertEqual(MODULE.available_slots(
            total_sumo=10, owned_sumo=0, reserved_runs=0, limit=15), 5)

    def test_owned_processes_are_already_covered_by_reservations(self):
        self.assertEqual(MODULE.available_slots(
            total_sumo=13, owned_sumo=5, reserved_runs=5, limit=15), 2)

    def test_capacity_never_goes_negative(self):
        self.assertEqual(MODULE.available_slots(
            total_sumo=15, owned_sumo=0, reserved_runs=1, limit=15), 0)


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_thesis_sqrt_flow_queue.py"
SPEC = importlib.util.spec_from_file_location("run_thesis_sqrt_flow_queue", SCRIPT)
QUEUE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUEUE)


class SqrtFlowQueueTests(unittest.TestCase):
    def test_accepts_pip_and_system_sumo_version_headers(self):
        self.assertTrue(QUEUE.sumo_version_matches("Eclipse SUMO sumo 1.28.0\n"))
        self.assertTrue(
            QUEUE.sumo_version_matches("Eclipse SUMO sumo Version 1.28.0\n")
        )
        self.assertFalse(QUEUE.sumo_version_matches("Eclipse SUMO sumo 1.18.0\n"))

    def test_initial_fifteen_are_300_then_500(self):
        tasks = QUEUE.build_ordered_tasks()
        self.assertEqual(
            tasks[:15],
            [*((300, seed) for seed in range(33, 43)),
             *((500, seed) for seed in range(43, 48))],
        )

    def test_remaining_queue_is_additional_500_then_700_then_1000(self):
        tasks = QUEUE.build_ordered_tasks()
        self.assertEqual(
            tasks[15:],
            [*((500, seed) for seed in (6, 8, 9, 10, 12)),
             *((700, seed) for seed in range(33, 43)),
             *((1000, seed) for seed in range(33, 43))],
        )

    def test_queue_has_exactly_40_unique_tasks(self):
        tasks = QUEUE.build_ordered_tasks()
        self.assertEqual(len(tasks), 40)
        self.assertEqual(len(set(tasks)), 40)


if __name__ == "__main__":
    unittest.main()

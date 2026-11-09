import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_thesis_shared_queue.py"
SPEC = importlib.util.spec_from_file_location("run_thesis_shared_queue", SCRIPT)
QUEUE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUEUE)


class SharedQueueTests(unittest.TestCase):
    def test_accepts_pip_and_system_sumo_version_headers(self):
        self.assertTrue(QUEUE.sumo_version_matches("Eclipse SUMO sumo 1.28.0\n"))
        self.assertTrue(QUEUE.sumo_version_matches("Eclipse SUMO sumo Version 1.28.0\n"))
        self.assertFalse(QUEUE.sumo_version_matches("Eclipse SUMO sumo 1.18.0\n"))

    def test_initial_fifteen_are_ten_integrated_then_five_utf(self):
        tasks = QUEUE.build_ordered_tasks(range(33, 43))
        self.assertEqual(
            tasks[:15],
            [*(('integrated', seed) for seed in range(33, 43)),
             *(('utf', seed) for seed in range(33, 38))],
        )

    def test_remaining_queue_finishes_utf_before_yamashita(self):
        tasks = QUEUE.build_ordered_tasks(range(33, 43))
        self.assertEqual(
            tasks[15:],
            [*(('utf', seed) for seed in range(38, 43)),
             *(('yamashita', seed) for seed in range(33, 43))],
        )


if __name__ == "__main__":
    unittest.main()

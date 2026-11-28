import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_eval35_lambda0525_shared_queue.py"
SPEC = importlib.util.spec_from_file_location("eval35_shared_queue", SCRIPT)
QUEUE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUEUE)

FINALIZER_SCRIPT = ROOT / "scripts" / "finalize_eval35_lambda0525_comparison.py"
FINALIZER_SPEC = importlib.util.spec_from_file_location(
    "eval35_finalizer", FINALIZER_SCRIPT
)
FINALIZER = importlib.util.module_from_spec(FINALIZER_SPEC)
FINALIZER_SPEC.loader.exec_module(FINALIZER)


class Eval35SharedQueueTests(unittest.TestCase):
    def test_queue_has_sixty_tasks_in_paper_condition_order(self):
        tasks = QUEUE.build_ordered_tasks(range(13, 23))
        self.assertEqual(len(tasks), 60)
        self.assertEqual(
            tasks[:4],
            [
                ("eval3-400-yamashita", 13),
                ("eval3-400-proposal", 13),
                ("eval3-400-yamashita", 14),
                ("eval3-400-proposal", 14),
            ],
        )
        self.assertTrue(all(tag.startswith("eval3-") for tag, _ in tasks[:40]))
        self.assertTrue(all(tag.startswith("eval5-") for tag, _ in tasks[40:]))

    def test_initial_fifteen_slots_are_all_eval3(self):
        tasks = QUEUE.build_ordered_tasks(range(13, 23))
        self.assertEqual(len(tasks[:15]), 15)
        self.assertTrue(all(tag.startswith("eval3-400-") for tag, _ in tasks[:15]))

    def test_fixed_input_templates_are_shared_by_the_two_methods(self):
        for condition in QUEUE.CONDITION_ORDER:
            specs = [
                spec for spec in QUEUE.CONTEXT_SPECS.values()
                if spec["condition"] == condition
            ]
            self.assertEqual(len(specs), 2)
            self.assertEqual(
                QUEUE.fixed_input_template(specs[0]),
                QUEUE.fixed_input_template(specs[1]),
            )

    def test_paired_summary_uses_the_same_seed_and_mean_ratio(self):
        rows = []
        for seed in FINALIZER.SEEDS:
            common = {
                "condition": "eval3-400",
                "seed": seed,
                "car_speed_mps": 7.0,
                "bus_speed_mps": 6.0,
                "stop_time_s": 10.0,
                "hard_brake_time_s": 1.0,
                "physical_collision_episodes": 0,
            }
            rows.append({**common, "method": "yamashita", "all_speed_mps": 5.0})
            rows.append({**common, "method": "proposal", "all_speed_mps": 5.5})
        report = FINALIZER.compare_condition("eval3-400", rows)
        self.assertAlmostEqual(report["speed_difference_mean_mps"], 0.5)
        self.assertAlmostEqual(report["speed_improvement_from_means_percent"], 10.0)
        self.assertEqual(report["proposal_faster_seed_count"], 10)
        self.assertEqual(report["paired_bootstrap_95_percent_mps"], [0.5, 0.5])

    def test_compact_result_selection_excludes_raw_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "results" / "runs" / "formal"
            output.mkdir(parents=True)
            for name in FINALIZER.COMPACT_TOP_LEVEL_FILES:
                (output / name).touch()
            for seed in FINALIZER.SEEDS:
                run = output / "eval5" / f"seed-{seed}"
                run.mkdir(parents=True)
                for name in FINALIZER.COMPACT_RUN_FILES:
                    (run / name).touch()
                checkpoint = run / "checkpoints" / "t0000060.0" / "checkpoint.json"
                checkpoint.parent.mkdir(parents=True)
                checkpoint.touch()
                for raw_name in FINALIZER.RAW_ARTIFACT_NAMES:
                    (run / raw_name).touch()
            context = {
                "tag": "formal",
                "root": root,
                "output": output,
                "spec": {"case": "eval5"},
            }

            selected = FINALIZER.compact_files(context)

            self.assertIn(output / "experiment-manifest.json", selected)
            self.assertTrue(any(path.name == "checkpoint.json" for path in selected))
            self.assertFalse(any(path.name in FINALIZER.RAW_ARTIFACT_NAMES for path in selected))


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_eval35_universal_lambda_sweep.py"
SPEC = importlib.util.spec_from_file_location("eval35_universal_lambda_sweep", SCRIPT)
SWEEP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SWEEP)


class Eval35UniversalLambdaSweepTests(unittest.TestCase):
    def test_queue_is_condition_then_lambda_then_seed(self):
        tasks = SWEEP.build_ordered_tasks()
        self.assertEqual(len(tasks), 220)
        self.assertEqual(
            tasks[:12],
            [
                *(('eval3-500', 0.0, seed) for seed in range(13, 23)),
                ('eval3-500', 0.1, 13),
                ('eval3-500', 0.1, 14),
            ],
        )
        self.assertEqual(tasks[109], ("eval3-500", 1.0, 22))
        self.assertEqual(tasks[110], ("eval5-300", 0.0, 13))
        self.assertEqual(tasks[219], ("eval5-300", 1.0, 22))

    def test_initial_slots_finish_first_lambda_cohort_early(self):
        tasks = SWEEP.build_ordered_tasks()[:15]
        self.assertEqual(tasks[:10], [("eval3-500", 0.0, seed) for seed in range(13, 23)])
        self.assertEqual(tasks[10:], [("eval3-500", 0.1, seed) for seed in range(13, 18)])

    def test_high_grid_uses_matched_seeds_and_skips_completed_merge_cohorts(self):
        tasks = SWEEP.build_ordered_tasks("high")
        expected = [
            (condition, value, seed)
            for condition, values, seeds in (
                ("eval3-500", (0.925, 0.95, 40 / 41, 80 / 81), range(13, 23)),
                ("eval5-300", (0.925, 0.95, 40 / 41, 80 / 81), range(13, 23)),
                ("eval7-1000", (0.925, 40 / 41), range(33, 43)),
            )
            for value in values
            for seed in seeds
        ]
        self.assertEqual(tasks, expected)

    def test_merge_flow_uses_paired_seeds_and_starts_with_two_complete_cohorts(self):
        tasks = SWEEP.build_ordered_tasks("merge-flow")
        expected_cohorts = {
            300: range(33, 43),
            500: range(43, 48),
            700: range(33, 43),
            1200: range(33, 43),
        }
        self.assertEqual(tasks, [
            (f"eval7-{flow}", 0.95, seed)
            for flow, seeds in expected_cohorts.items()
            for seed in seeds
        ])
        for flow, seeds in expected_cohorts.items():
            for seed in seeds:
                self.assertEqual(
                    SWEEP.fixed_input_template(f"eval7-{flow}").format(seed=seed),
                    f"fixed_inputs/thesis/eval7-flow-sweep/requesting-{flow}-accepting-1000/seed-{seed}.jsonl",
                )

    def test_fixed_inputs_are_condition_specific(self):
        for condition in SWEEP.CONDITION_ORDER:
            path = SWEEP.fixed_input_template(condition)
            self.assertIn(condition, path)
            self.assertTrue(path.endswith("seed-{seed}.jsonl"))

    def test_lambda_tags_cover_zero_to_one(self):
        self.assertEqual([SWEEP.lambda_tag(value) for value in SWEEP.LAMBDAS], [
            "000", "010", "020", "030", "040", "050",
            "060", "070", "080", "090", "100",
        ])

    def test_sumo_home_requires_binary_and_traci_package(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            sumo_home = Path(temporary_directory)
            (sumo_home / "bin").mkdir()
            (sumo_home / "bin" / "sumo").touch()
            with self.assertRaisesRegex(RuntimeError, "tools/traci/__init__.py"):
                SWEEP.validate_sumo_home_layout(sumo_home)

            (sumo_home / "tools" / "traci").mkdir(parents=True)
            (sumo_home / "tools" / "traci" / "__init__.py").touch()
            SWEEP.validate_sumo_home_layout(sumo_home)


if __name__ == "__main__":
    unittest.main()

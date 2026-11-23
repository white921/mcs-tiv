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
        self.assertEqual(len(tasks), 330)
        self.assertEqual(
            tasks[:12],
            [
                *(('eval3-400', 0.0, seed) for seed in range(13, 23)),
                ('eval3-400', 0.1, 13),
                ('eval3-400', 0.1, 14),
            ],
        )
        self.assertEqual(tasks[109], ("eval3-400", 1.0, 22))
        self.assertEqual(tasks[110], ("eval3-500", 0.0, 13))
        self.assertEqual(tasks[220], ("eval5-300", 0.0, 13))

    def test_initial_slots_finish_first_lambda_cohort_early(self):
        tasks = SWEEP.build_ordered_tasks()[:15]
        self.assertEqual(tasks[:10], [("eval3-400", 0.0, seed) for seed in range(13, 23)])
        self.assertEqual(tasks[10:], [("eval3-400", 0.1, seed) for seed in range(13, 18)])

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

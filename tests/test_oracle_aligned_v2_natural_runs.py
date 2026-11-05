import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "analyze_oracle_aligned_v2_natural_runs",
    ROOT / "scripts" / "analyze_oracle_aligned_v2_natural_runs.py")
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


class OracleAlignedV2NaturalRunsTest(unittest.TestCase):
    def rows(self):
        return [
            {"case": case, "seed": seed, "difference": float(seed - 22)}
            for case in analysis.CASES for seed in analysis.SEEDS
        ]

    def test_macro_case_mean_equal_weights_cases(self):
        self.assertEqual(analysis.macro_case_mean(self.rows(), "difference"), 5.5)

    def test_paired_seed_bootstrap_is_deterministic(self):
        first = analysis.paired_seed_bootstrap(
            self.rows(), "difference", 100, 20261105)
        second = analysis.paired_seed_bootstrap(
            self.rows(), "difference", 100, 20261105)
        self.assertEqual(first, second)

    def test_collision_episodes_are_a_reported_metric(self):
        self.assertIn("physical_collision_episodes", analysis.METRICS)


if __name__ == "__main__":
    unittest.main()

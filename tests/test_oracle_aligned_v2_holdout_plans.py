import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prepare_oracle_aligned_v2_holdout_plans",
    ROOT / "scripts" / "prepare_oracle_aligned_v2_holdout_plans.py")
plans = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plans)


class OracleAlignedV2HoldoutPlansTest(unittest.TestCase):
    def test_preregistered_shape_is_eight_plans_and_960_events(self):
        self.assertEqual(len(plans.SEED_GROUPS), 2)
        self.assertEqual(len(plans.WINDOWS), 4)
        self.assertEqual(2 * 4 * 120, 960)
        self.assertEqual(plans.SAMPLING_SEED, 20261105)

    def test_seed_groups_are_unique_and_unused_development_seeds(self):
        values = [seed for group in plans.SEED_GROUPS for seed in group]
        self.assertEqual(values, list(range(23, 33)))


if __name__ == "__main__":
    unittest.main()

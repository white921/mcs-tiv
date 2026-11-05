import importlib.util
import json
from pathlib import Path
import tempfile
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

    def test_discovery_audit_requires_completed_clean_fixed_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = {
                "status": "completed", "completed_simulations": 30,
                "failed_simulations": 0, "duration_s": 300.0,
                "workers": 10, "cases": ["eval3", "eval5", "eval7"],
                "tasks": [{"seed": seed} for seed in range(23, 33)],
                "git": {"commit": plans.DISCOVERY_SOURCE_COMMIT,
                        "dirty": False},
                "method": "yamashita-baseline",
            }
            (root / "experiment-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8")

            audited = plans.validate_discovery(root, "yamashita")

            self.assertEqual(
                audited["source_commit"], plans.DISCOVERY_SOURCE_COMMIT)

    def test_discovery_audit_rejects_incomplete_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "experiment-manifest.json").write_text(
                json.dumps({"status": "running", "duration_s": 300}),
                encoding="utf-8")

            with self.assertRaises(ValueError):
                plans.validate_discovery(root, "proposal")


if __name__ == "__main__":
    unittest.main()

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
sys.path.insert(0, str(ROOT / "scripts"))

from fixed_vehicle_inputs import load_fixed_vehicle_input
from generate_universal_lambda095_holdout_inputs import (
    CONDITIONS,
    GENERATION_PYTHON,
    SEEDS,
    expected_files,
)


class UniversalLambda095HoldoutInputTests(unittest.TestCase):
    def test_committed_files_match_preregistered_conditions(self):
        root = (
            ROOT
            / "fixed_inputs"
            / "thesis"
            / "universal-lambda095-holdout"
        )
        expected_paths = {path for path, _ in expected_files(root)}
        self.assertEqual(set(root.glob("*/*.jsonl")), expected_paths)
        for path, expected in expected_files(root):
            with self.subTest(path=path):
                self.assertEqual(path.read_text(encoding="utf-8"), expected)
                condition = path.parent.name
                case, flows = CONDITIONS[condition]
                seed = int(path.stem.split("-")[1])
                schedule = load_fixed_vehicle_input(
                    path,
                    expected_case=case,
                    expected_seed=seed,
                    expected_flows_vph=flows,
                    expected_bus_share=0.25,
                    prefix_duration_s=600,
                )
                self.assertEqual(
                    schedule.metadata["generated_with_python"],
                    GENERATION_PYTHON,
                )
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    hashlib.sha256(expected.encode()).hexdigest(),
                )

    def test_seed_set_is_fixed_before_results(self):
        self.assertEqual(SEEDS, tuple(range(23, 33)))

    def test_each_condition_has_ten_inputs(self):
        root = (
            ROOT
            / "fixed_inputs"
            / "thesis"
            / "universal-lambda095-holdout"
        )
        for condition in CONDITIONS:
            self.assertEqual(
                sorted(path.name for path in (root / condition).glob("*.jsonl")),
                [f"seed-{seed}.jsonl" for seed in SEEDS],
            )


if __name__ == "__main__":
    unittest.main()

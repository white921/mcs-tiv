import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "time_stratified_analysis",
    ROOT / "scripts" / "analyze_time_stratified_decision_oracle.py",
)
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


class TimeStratifiedAnalysisTest(unittest.TestCase):
    def rows(self):
        rows = []
        for case_index, case in enumerate(analysis.CASES, 1):
            for window_index, window in enumerate(analysis.WINDOWS, 1):
                for seed in (13, 14):
                    rows.append({
                        "case": case,
                        "window": window,
                        "origin_policy": "yamashita",
                        "seed": seed,
                        "baseline_regret_m": float(case_index),
                        "proposal_regret_m": float(window_index),
                        "proposal_minus_baseline_regret_m": float(
                            window_index - case_index
                        ),
                    })
        return rows

    def test_macro_cell_mean_equal_weights_cases_and_windows(self):
        rows = self.rows()
        self.assertEqual(
            analysis.macro_cell_mean(rows, "baseline_regret_m"), 2.0
        )
        self.assertEqual(
            analysis.macro_cell_mean(rows, "proposal_regret_m"), 2.5
        )

    def test_cluster_bootstrap_is_deterministic(self):
        rows = self.rows()
        first = analysis.cluster_bootstrap(
            rows, "proposal_minus_baseline_regret_m", 100, 20261103
        )
        second = analysis.cluster_bootstrap(
            rows, "proposal_minus_baseline_regret_m", 100, 20261103
        )
        self.assertEqual(first, second)
        self.assertTrue(all(value == 0.5 for value in first))

    def test_percentile_uses_nearest_rank(self):
        self.assertEqual(analysis.percentile(list(range(1, 101)), 0.95), 95)

    def test_expected_plan_hashes_support_new_preregistered_seed_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hashes.json"
            path.write_text(json.dumps({"23-27:0-100": "a" * 64}))
            self.assertEqual(
                analysis.load_expected_plan_hashes(path),
                {(23, 27, "0-100"): "a" * 64},
            )

    def test_physical_collisions_are_valid_when_logs_match_summaries(self):
        self.assertTrue(analysis.collision_counts_consistent(2, 2, 2))
        self.assertFalse(analysis.collision_counts_consistent(2, 0, 2))

    def test_holdout_diagnostics_count_invalid_fallback_and_collisions(self):
        rows = [
            {"oracle_valid": True,
             "oracle_aligned_v2_fallback_to_yamashita": True,
             "accept_physical_collision_records": 0,
             "reject_physical_collision_records": 0},
            {"oracle_valid": False, "oracle_invalid_reason": "accept:safety_invalid",
             "oracle_aligned_v2_fallback_to_yamashita": False,
             "accept_physical_collision_records": 2,
             "reject_physical_collision_records": 0},
        ]
        result = analysis.holdout_diagnostics(rows)
        self.assertEqual(result["oracle_valid_events"], 1)
        self.assertEqual(result["oracle_invalid_events"], 1)
        self.assertEqual(result["oracle_aligned_v2_fallback_events"], 1)
        self.assertEqual(result["accept_physical_collision_records"], 2)


if __name__ == "__main__":
    unittest.main()

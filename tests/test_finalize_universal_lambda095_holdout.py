from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import finalize_universal_lambda095_holdout as FINALIZER


class FinalizeUniversalLambda095HoldoutTests(unittest.TestCase):
    def rows_for(self, condition, yamashita_speed, proposal_speed):
        rows = []
        for seed in FINALIZER.SCHEDULER.SEEDS:
            common = {
                "condition": condition,
                "seed": seed,
                "car_speed_mps": 7.0,
                "bus_speed_mps": 6.0,
                "stop_time_s": 10.0,
                "hard_brake_time_s": 1.0,
                "physical_collision_episodes": 0,
                "fixed_input_sha256": f"input-{condition}-{seed}",
            }
            rows.append(
                {**common, "method": "yamashita", "all_speed_mps": yamashita_speed}
            )
            rows.append(
                {**common, "method": "proposal", "all_speed_mps": proposal_speed}
            )
        return rows

    def test_paired_comparison_uses_same_seed_and_input(self):
        rows = self.rows_for("eval3-500", 5.0, 5.5)
        report = FINALIZER.paired_comparison("eval3-500", rows)
        self.assertAlmostEqual(report["speed_difference_mean_mps"], 0.5)
        self.assertAlmostEqual(
            report["speed_improvement_from_means_percent"], 10.0
        )
        self.assertEqual(report["proposal_faster_seed_count"], 10)
        self.assertEqual(report["paired_bootstrap_95_percent_mps"], [0.5, 0.5])

    def test_summary_balances_topologies_equally(self):
        rows = []
        rows.extend(self.rows_for("eval3-500", 5.0, 5.5))
        rows.extend(self.rows_for("eval5-300", 10.0, 10.5))
        rows.extend(self.rows_for("eval7-1000", 4.0, 3.8))
        summary = FINALIZER.build_summary(rows, "a" * 40)
        self.assertAlmostEqual(
            summary["topology_balanced_relative_improvement_percent"],
            (10.0 + 5.0 - 5.0) / 3,
        )
        self.assertAlmostEqual(
            summary["worst_condition_relative_improvement_percent"], -5.0
        )
        self.assertFalse(summary["proposal_faster_in_all_conditions"])

    def test_input_mismatch_is_rejected(self):
        rows = self.rows_for("eval3-500", 5.0, 5.5)
        proposal = next(row for row in rows if row["method"] == "proposal")
        proposal["fixed_input_sha256"] = "different"
        with self.assertRaisesRegex(RuntimeError, "fixed input mismatch"):
            FINALIZER.paired_comparison("eval3-500", rows)


if __name__ == "__main__":
    unittest.main()

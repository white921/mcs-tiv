from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_eval7_lambda_merge_delay as AUDIT


class AuditEval7LambdaMergeDelayTests(unittest.TestCase):
    def test_summary_value_reads_merge_group_speed(self):
        stderr = "requesting_speed : 3.25\naccepting_speed : 9.5\n"
        self.assertEqual(AUDIT.summary_value(stderr, "requesting_speed"), 3.25)
        self.assertEqual(AUDIT.summary_value(stderr, "accepting_speed"), 9.5)

    def test_summary_value_requires_named_line(self):
        with self.assertRaisesRegex(RuntimeError, "missing requesting_speed"):
            AUDIT.summary_value("all_speed : 5.0\n", "requesting_speed")

    def test_summary_pairs_same_seed_and_lambda(self):
        rows = []
        for value in AUDIT.LAMBDAS:
            for seed in AUDIT.SEEDS:
                rows.append(
                    {
                        "lambda": value,
                        "seed": seed,
                        "all_speed_mps": 5.0 + value,
                        "requesting_speed_mps": 3.0 + value,
                        "accepting_speed_mps": 8.0 + value,
                        "stop_time_s": 100.0 - value,
                        "hard_brake_time_s": 1.0,
                        "physical_collision_episodes": 0,
                        "fixed_input_sha256": f"seed-{seed}",
                        "checks": {"complete": True},
                        "errors": [],
                    }
                )
        summary = AUDIT.build_summary(rows, "a" * 40)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["run_count"], 4)
        self.assertAlmostEqual(
            summary["paired"][0]["accepting_speed_difference_mps"], 0.425
        )

    def test_input_mismatch_is_rejected(self):
        rows = []
        for value in AUDIT.LAMBDAS:
            for seed in AUDIT.SEEDS:
                rows.append(
                    {
                        "lambda": value,
                        "seed": seed,
                        "all_speed_mps": 5.0,
                        "requesting_speed_mps": 3.0,
                        "accepting_speed_mps": 8.0,
                        "stop_time_s": 100.0,
                        "hard_brake_time_s": 1.0,
                        "physical_collision_episodes": 0,
                        "fixed_input_sha256": f"{value}-{seed}",
                        "checks": {"complete": True},
                        "errors": [],
                    }
                )
        with self.assertRaisesRegex(RuntimeError, "fixed input mismatch"):
            AUDIT.build_summary(rows, "a" * 40)


if __name__ == "__main__":
    unittest.main()

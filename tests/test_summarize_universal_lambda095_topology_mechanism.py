import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import summarize_universal_lambda095_topology_mechanism as SUMMARY


class SummarizeUniversalLambda095TopologyMechanismTests(unittest.TestCase):
    def audit(self, counts, records):
        return {
            "convex_lambda": 0.95,
            "counts": counts,
            "records": records,
        }

    def test_summarizes_exact_counts_and_retained_records_separately(self):
        audits = [
            self.audit(
                {
                    "active_attempts": 10,
                    "active_evaluations": 8,
                    "active_unsupported": 2,
                    "decision_agreement": 6,
                    "decision_disagreement": 2,
                    "proposal_accept": 3,
                    "proposal_reject": 5,
                    "tiv_would_accept": 4,
                    "tiv_would_reject": 4,
                },
                [
                    {
                        "status": "evaluated",
                        "follower_count": 2,
                        "z_time": -0.2,
                        "z_follow": 0.1,
                    },
                    {
                        "status": "unsupported",
                        "reason": "missing heading",
                    },
                ],
            ),
            self.audit(
                {
                    "active_attempts": 5,
                    "active_evaluations": 4,
                    "active_unsupported": 1,
                    "decision_agreement": 3,
                    "decision_disagreement": 1,
                    "proposal_accept": 1,
                    "proposal_reject": 3,
                    "tiv_would_accept": 2,
                    "tiv_would_reject": 2,
                },
                [
                    {
                        "status": "evaluated",
                        "follower_count": 4,
                        "z_time": 0.4,
                        "z_follow": -0.2,
                    },
                    {
                        "status": "unsupported",
                        "reason": "missing heading",
                    },
                ],
            ),
        ]
        report = SUMMARY.summarize_audits(audits)
        self.assertEqual(report["exact_counts"]["active_attempts"], 15)
        self.assertEqual(report["exact_counts"]["decision_disagreement"], 3)
        self.assertAlmostEqual(report["exact_rates"]["unsupported_rate"], 0.2)
        sample = report["retained_record_sample"]
        self.assertTrue(sample["is_truncated"])
        self.assertEqual(sample["unsupported_reasons"], {"missing heading": 2})
        self.assertEqual(sample["follower_count_mean"], 3)
        self.assertEqual(sample["follower_count_median"], 3)
        self.assertAlmostEqual(sample["mean_abs_weighted_time"], 0.015)
        self.assertAlmostEqual(sample["mean_abs_weighted_follow"], 0.1425)
        self.assertTrue(
            math.isclose(sample["weighted_follow_to_time_ratio"], 9.5)
        )

    def test_rejects_audit_without_evaluated_records(self):
        audit = self.audit(
            {"active_attempts": 1, "active_unsupported": 1},
            [{"status": "unsupported", "reason": "missing heading"}],
        )
        with self.assertRaisesRegex(RuntimeError, "no retained evaluated records"):
            SUMMARY.summarize_audits([audit])


if __name__ == "__main__":
    unittest.main()

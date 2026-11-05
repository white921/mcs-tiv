import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "analyze_oracle_aligned_v2_gate",
    ROOT / "scripts" / "analyze_oracle_aligned_v2_gate.py")
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


class OracleAlignedV2GateAnalysisTest(unittest.TestCase):
    def row(self, baseline="accept", predicted=-11.0, actual=-4.0):
        return {
            "case": "eval3", "window": "0-100",
            "origin_policy": "proposal", "seed": 13, "ordinal": 1,
            "predicted_m": predicted, "actual_m": actual,
            "baseline_choice": baseline,
            "oracle_choice": "accept" if actual > 0 else "reject",
            "yamashita_choice": "accept",
        }

    def test_accept_to_reject_gate_requires_strict_threshold(self):
        self.assertEqual(
            analysis.gated_choice(self.row(predicted=-10.0), 10,
                                  "accept_to_reject"),
            "accept")
        self.assertEqual(
            analysis.gated_choice(self.row(predicted=-10.1), 10,
                                  "accept_to_reject"),
            "reject")

    def test_accept_to_reject_gate_never_reverses_reject(self):
        row = self.row(baseline="reject", predicted=100.0, actual=4.0)
        self.assertEqual(
            analysis.gated_choice(row, 10, "accept_to_reject"), "reject")

    def test_regret_uses_realised_distance_gap(self):
        row = self.row(actual=-4.0)
        self.assertEqual(analysis.regret(row, "reject"), 0.0)
        self.assertEqual(analysis.regret(row, "accept"), 4.0)

    def test_tie_regret_still_uses_the_small_realised_gap(self):
        row = self.row(actual=0.2)
        row["oracle_choice"] = "tie"
        self.assertEqual(analysis.regret(row, "accept"), 0.0)
        self.assertEqual(analysis.regret(row, "reject"), 0.2)


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "analyze_oracle_aligned_v2_diagnostics",
    ROOT / "scripts" / "analyze_oracle_aligned_v2_diagnostics.py")
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


class OracleAlignedV2DiagnosticsTest(unittest.TestCase):
    def row(self, baseline="accept", predicted="-11", actual="-5"):
        return {
            "case": "eval3", "window": "0-100", "origin_policy": "proposal",
            "seed": "13", "ordinal": "2", "arrival_only_choice": baseline,
            "predicted_accept_minus_reject_m": predicted,
            "actual_accept_minus_reject_m": actual,
        }

    def test_categories_distinguish_useful_and_harmful_directions(self):
        self.assertEqual(analysis.category(self.row()), "fixed_gate_correct")
        self.assertEqual(
            analysis.category(self.row(actual="5")), "fixed_gate_harm")
        self.assertEqual(
            analysis.category(self.row(baseline="reject", predicted="11")),
            "rejected_reverse_harm")

    def test_strict_ten_metre_threshold(self):
        self.assertIsNone(analysis.category(self.row(predicted="-10")))

    def test_unscored_breakdown_preserves_all_rows(self):
        rows = [self.row(), self.row(predicted="", actual="0")]
        result = analysis.unscored_breakdown(rows)
        self.assertEqual(result["events"], 2)
        self.assertEqual(result["scored"], 1)
        self.assertEqual(result["unscored"], 1)


if __name__ == "__main__":
    unittest.main()

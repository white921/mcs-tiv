import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rescore_oracle_aligned_v2 as rescore


class OracleAlignedV2RescoreTests(unittest.TestCase):
    def test_fixed_window_boundaries(self):
        self.assertEqual(rescore.window_for(0.0), "0-100")
        self.assertEqual(rescore.window_for(99.9), "0-100")
        self.assertEqual(rescore.window_for(100.0), "100-160")
        self.assertEqual(rescore.window_for(160.0), "160-220")
        self.assertEqual(rescore.window_for(220.0), "220-290")
        self.assertEqual(rescore.window_for(290.0), "220-290")
        with self.assertRaises(ValueError):
            rescore.window_for(290.1)

    def test_discovery_keeps_only_completed_event_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event = root / (
                "follower-impact-time-stratified-test/events/001/inner")
            event.mkdir(parents=True)
            (event / "manifest.json").write_text(json.dumps({
                "schema": "decision-oracle-event-v2",
            }), encoding="utf-8")
            ignored = root / (
                "follower-impact-time-stratified-test/events/002/inner")
            ignored.mkdir(parents=True)
            (ignored / "manifest.json").write_text(json.dumps({
                "schema": "other",
            }), encoding="utf-8")

            self.assertEqual(
                rescore.discover_events(root), [event / "manifest.json"])

    def test_unavailable_v2_evaluation_remains_an_unscored_row(self):
        manifest = {
            "event": {
                "case": "eval3", "origin_policy": "yamashita",
                "seed": 13, "ordinal": 1, "sim_time_s": 20.0,
            },
            "proposal_evaluation": None,
            "oracle": {
                "choice": "tie", "accept_minus_reject_distance_m": 0.0,
            },
            "policy_choices": {
                policy: None for policy in rescore.POLICIES
            },
            "policy_scores": {},
        }

        row = rescore.event_row(manifest)

        self.assertIsNone(row["predicted_accept_minus_reject_m"])
        self.assertIsNone(row["oracle_aligned_v2_regret_m"])
        self.assertIsNone(row["follower_count"])


if __name__ == "__main__":
    unittest.main()

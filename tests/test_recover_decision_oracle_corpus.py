import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import recover_decision_oracle_corpus as recovery


class RecoverDecisionOracleCorpusTests(unittest.TestCase):
    def test_collects_only_complete_matching_event_artifacts(self):
        event = {
            "case": "eval3", "origin_policy": "proposal", "seed": 28,
            "ordinal": 7, "sim_time_s": 42.0, "receiver_id": "2",
            "sender_id": "1", "desired_path_id": "1_3",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            slug = "001-eval3-proposal-seed-28-event-0007"
            event_root = output / "events" / slug
            inner = event_root / "eval3-proposal-seed-28-event-0007"
            inner.mkdir(parents=True)
            (event_root / "manifest.json").write_text(json.dumps({
                "schema": "decision-oracle-experiment-v2", "event_count": 1,
                "exit_code": 0, "source_unchanged": True,
            }))
            (inner / "manifest.json").write_text(json.dumps({
                "schema": "decision-oracle-event-v2", "event": event,
                "git": {"commit": "source", "dirty": False},
                "branches": {
                    name: {"completed": True,
                           "restore_fingerprint_match": True}
                    for name in ("accept", "reject")
                },
            }))

            results, manifests = recovery.collect_completed_events(
                output, [event], "source")

        self.assertEqual(len(results), 1)
        self.assertEqual(len(manifests), 1)
        self.assertTrue(results[0]["recovered_from_completed_artifact"])

    def test_rejects_incomplete_branch(self):
        event = {
            "case": "eval3", "origin_policy": "proposal", "seed": 28,
            "ordinal": 7, "sim_time_s": 42.0, "receiver_id": "2",
            "sender_id": "1", "desired_path_id": "1_3",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            event_root = output / "events/001-eval3-proposal-seed-28-event-0007"
            inner = event_root / "event"
            inner.mkdir(parents=True)
            (event_root / "manifest.json").write_text(json.dumps({
                "schema": "decision-oracle-experiment-v2", "event_count": 1,
                "exit_code": 0, "source_unchanged": True,
            }))
            (inner / "manifest.json").write_text(json.dumps({
                "schema": "decision-oracle-event-v2", "event": event,
                "git": {"commit": "source", "dirty": False},
                "branches": {
                    "accept": {"completed": True,
                               "restore_fingerprint_match": True},
                    "reject": {"completed": False,
                               "restore_fingerprint_match": True},
                },
            }))

            with self.assertRaisesRegex(ValueError, "incomplete reject branch"):
                recovery.collect_completed_events(output, [event], "source")


if __name__ == "__main__":
    unittest.main()

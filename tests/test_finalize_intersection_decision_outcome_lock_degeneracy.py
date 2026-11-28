import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "outcome_lock_degeneracy_finalizer",
    ROOT / "scripts" /
    "finalize_intersection_decision_outcome_lock_degeneracy.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DecisionOutcomeLockDegeneracyFinalizerTest(unittest.TestCase):
    def test_trace_revisits_distinguishes_accept_and_reject_keys(self):
        records = [
            {
                "event": "decision", "reason": "normalized-deceleration-propagation",
                "accept": True, "sim_time": 1.0, "receiver_id": "r",
                "sender_id": "s", "desired_path_id": "p1",
            },
            {
                "event": "suppressed", "reason": "decision_locked",
                "sim_time": 1.1, "receiver_id": "r", "sender_id": "s",
                "desired_path_id": "p1",
            },
            {
                "event": "decision", "reason": "normalized-deceleration-propagation",
                "accept": False, "sim_time": 2.0, "receiver_id": "r",
                "sender_id": "s", "desired_path_id": "p2",
            },
            {
                "event": "decision", "reason": "normalized-deceleration-propagation",
                "accept": False, "sim_time": 2.1, "receiver_id": "r",
                "sender_id": "s", "desired_path_id": "p3",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "negotiations.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            result = MODULE.trace_lock_revisits(path)
        self.assertEqual(result["normalized_accept_decisions"], 1)
        self.assertEqual(result["normalized_reject_decisions"], 2)
        self.assertEqual(
            result["accept_decisions_with_same_key_event_under_1s"], 1)
        self.assertEqual(
            result["reject_decisions_with_same_key_event_under_1s"], 0)

    def test_outer_manifest_requires_explicit_redundant_arm_omission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "status": "stopped_after_wave_1",
                "source_commit": "source",
                "automatic_rerun": False,
                "completed_waves": [{
                    "arm": MODULE.ARM,
                    "results": [{"returncode": 0}] * 3,
                }],
                "omitted_waves": [{
                    "arm": MODULE.OMITTED_ARM,
                    "reason": "reject_lock_key_unreachable",
                }],
            }
            (root / "experiment-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8")
            result = MODULE.validate_outer_manifest(root, "source")
            self.assertEqual(result["status"], "stopped_after_wave_1")
            manifest["omitted_waves"][0]["reason"] = "unknown"
            (root / "experiment-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "omitted-arm reason"):
                MODULE.validate_outer_manifest(root, "source")


if __name__ == "__main__":
    unittest.main()

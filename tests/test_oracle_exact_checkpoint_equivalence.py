import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_oracle_exact_checkpoint_equivalence",
    ROOT / "scripts" / "validate_oracle_exact_checkpoint_equivalence.py")
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


class OracleExactCheckpointEquivalenceTest(unittest.TestCase):
    def test_cli_exposes_audited_checkpoint_source_override(self):
        source = (ROOT / "scripts" /
                  "validate_oracle_exact_checkpoint_equivalence.py").read_text()

        self.assertIn("--allow-checkpoint-source-commit", source)
        self.assertIn("--checkpoint-compatibility-note", source)
        self.assertIn("checkpoint_source_compatibility", source)

    def test_equal_event_manifests_pass(self):
        event = {
            "event": {"case": "eval3"},
            "policy_choices": {"oracle_aligned_v2": "reject"},
            "actor_vehicle_ids": ["1", "2"],
            "follower_vehicle_ids": ["3"],
            "cohort_vehicle_ids": ["1", "2", "3"],
            "oracle": {"choice": "reject", "valid": True},
            "boundary_fingerprint": "abc",
            "branches": {
                branch: {
                    "metrics": {"distance_m": 10.0, "hard_brake_time_s": 0.0,
                                "stop_time_s": 0.0},
                    "safety": {"valid": True, "physical_collision_records": 0},
                }
                for branch in ("accept", "reject")
            },
        }
        result = validation.compare(event, event)
        self.assertTrue(result["equivalent"])
        self.assertTrue(result["cross_process_boundary_fingerprint_match"])

    def test_boundary_fingerprint_mismatch_fails(self):
        reference = {
            "event": {"case": "eval3"},
            "policy_choices": {"oracle_aligned_v2": "reject"},
            "actor_vehicle_ids": ["1", "2"],
            "follower_vehicle_ids": ["3"],
            "cohort_vehicle_ids": ["1", "2", "3"],
            "oracle": {"choice": "reject", "valid": True},
            "boundary_fingerprint": "from-start",
            "branches": {
                branch: {
                    "metrics": {"distance_m": 10.0, "hard_brake_time_s": 0.0,
                                "stop_time_s": 0.0},
                    "safety": {"valid": True, "physical_collision_records": 0},
                }
                for branch in ("accept", "reject")
            },
        }
        exact = {**reference, "boundary_fingerprint": "checkpoint"}
        result = validation.compare(reference, exact)
        self.assertFalse(result["equivalent"])
        self.assertFalse(result["cross_process_boundary_fingerprint_match"])
        self.assertIn("boundary_fingerprint", result["differences"])

    def test_worker_exception_is_preserved_as_failed_result(self):
        event = {"case": "eval7", "origin_policy": "proposal", "seed": 23}
        with mock.patch.object(
                validation, "run_event", side_effect=RuntimeError("boom")):
            result = validation.run_event_safe(event, object())
        self.assertFalse(result["equivalent"])
        self.assertEqual(result["event"], event)
        self.assertEqual(result["exception"], "RuntimeError: boom")


if __name__ == "__main__":
    unittest.main()

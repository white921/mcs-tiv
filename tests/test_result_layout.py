import argparse
import datetime
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_thesis_batch", ROOT / "scripts" / "run_thesis_batch.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class ResultLayoutTests(unittest.TestCase):
    def args(self, **updates):
        values = {
            "run_name": None,
            "deceleration_active": True,
            "deceleration_time_half_life": 0.0,
            "deceleration_loss_lambda": 1.0,
            "cases": ["eval3"],
            "seeds": [1, 2, 3, 4, 5],
            "seeds_per_case": None,
            "duration": 600,
            "eval7_flows": None,
        }
        values.update(updates)
        return argparse.Namespace(**values)

    def test_default_directory_is_one_named_child_of_results_runs(self):
        now = datetime.datetime(
            2026, 10, 26, 15, 30, 0,
            tzinfo=datetime.timezone(datetime.timedelta(hours=9)))

        path = RUNNER.default_run_directory(self.args(), now=now)

        self.assertEqual(path.parent, ROOT / "results" / "runs")
        self.assertEqual(
            path.name,
            "20261026T153000+0900__proposal__eval3__600s__seeds-1-2-3-4-5")

    def test_run_name_is_sanitized_but_remains_readable(self):
        path = RUNNER.default_run_directory(
            self.args(run_name=" Eval.3 提案 / seed 1〜5 "))

        self.assertEqual(path.parent, ROOT / "results" / "runs")
        self.assertEqual(path.name, "Eval.3-提案-seed-1-5")

    def test_weighted_run_directory_records_half_life(self):
        now = datetime.datetime(
            2026, 10, 26, 15, 30, 0,
            tzinfo=datetime.timezone(datetime.timedelta(hours=9)))

        path = RUNNER.default_run_directory(
            self.args(deceleration_time_half_life=3.0), now=now)

        self.assertIn("proposal-weighted-3s", path.name)

    def test_write_json_has_stable_trailing_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            RUNNER.write_json(path, {"status": "completed"})
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '{\n  "status": "completed"\n}\n')

    def test_experiment_environment_does_not_inherit_mcs_switches_or_paths(self):
        stale = {
            "PATH": "/usr/bin",
            "MCS_PRIORITY_HOLD_MODE": "conditional",
            "MCS_DECELERATION_MODE": "active",
            "MCS_DECELERATION_TIME_HALF_LIFE_S": "99",
            "MCS_DECELERATION_LOSS_LAMBDA": "99",
            "MCS_FCD_OUTPUT": "/tmp/old-fcd.xml",
            "MCS_CHECKPOINT_DIR": "/tmp/old-checkpoint",
        }

        cleaned = RUNNER.clean_experiment_environment(stale)

        self.assertEqual(cleaned, {"PATH": "/usr/bin"})

    def test_lane_aware_run_explicitly_records_priority_hold_as_off(self):
        self.assertEqual(
            RUNNER.PRIORITY_HOLD_MANIFEST,
            {"mode": "off", "enabled": False})

    def test_manifest_records_oracle_aligned_v2_rule(self):
        manifest = RUNNER.deceleration_prediction_manifest(
            self.args(deceleration_loss_lambda=1.25))

        self.assertEqual(
            manifest["decision_rule"], "oracle-aligned-reject-gated-v2")
        self.assertEqual(manifest["reject_override_threshold_m"], 10.0)
        self.assertIn("never overridden", manifest["decision_formula"])
        self.assertEqual(
            manifest["distance_scope"],
            "request, receiver, and detected follower union")
        self.assertEqual(
            manifest["legacy_time_equivalent_loss_lambda_for_diagnostics"],
            1.25)

    def test_eval7_flow_override_selects_matching_fixed_input(self):
        details = RUNNER.fixed_input_details(
            "eval7", 6, 300, "fixed", prefix_duration=300,
            flows=(500, 1000))

        self.assertEqual(
            details["relative_path"],
            "fixed_inputs/thesis/eval7-flow-sweep/"
            "requesting-500-accepting-1000/seed-6.jsonl")
        self.assertEqual(details["prefix_duration_s"], 300.0)


if __name__ == "__main__":
    unittest.main()

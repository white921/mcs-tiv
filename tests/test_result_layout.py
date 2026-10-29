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
            "eval3_downstream_slow_zone": False,
            "eval3_slow_zone_location": "downstream",
            "eval3_slow_zone_start_offset": 15.0,
            "eval3_slow_zone_length": 2.0,
            "eval3_slow_zone_speed_limit": 8.33,
            "cases": ["eval3"],
            "seeds": [1, 2, 3, 4, 5],
            "seeds_per_case": None,
            "duration": 600,
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
            "MCS_EVAL3_DOWNSTREAM_SLOW_ZONE": "1",
        }

        cleaned = RUNNER.clean_experiment_environment(stale)

        self.assertEqual(cleaned, {"PATH": "/usr/bin"})

    def test_lane_aware_run_explicitly_records_priority_hold_as_off(self):
        self.assertEqual(
            RUNNER.PRIORITY_HOLD_MANIFEST,
            {"mode": "off", "enabled": False})

    def test_manifest_records_time_equivalent_loss_lambda(self):
        manifest = RUNNER.deceleration_prediction_manifest(
            self.args(deceleration_loss_lambda=1.25))

        self.assertEqual(manifest["loss_lambda"], 1.25)
        self.assertIn("accept iff M<=0", manifest["decision_formula"])
        self.assertEqual(
            manifest["loss_scope"],
            "detected followers excluding request and receiver vehicles")
        self.assertEqual(
            manifest["excluded_loss_roles"],
            ["request_vehicle", "receiver_vehicle"])

    def test_slow_zone_is_named_and_recorded_independently_of_method(self):
        now = datetime.datetime(
            2026, 10, 26, 15, 30, 0,
            tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
        args = self.args(
            deceleration_active=False,
            eval3_downstream_slow_zone=True,
        )

        path = RUNNER.default_run_directory(args, now=now)
        scenario = RUNNER.eval3_slow_zone_manifest(args)

        self.assertIn("yamashita-downstream-slow-zone", path.name)
        self.assertEqual(scenario["edge_id"], "right")
        self.assertEqual(scenario["speed_limit_mps"], 8.33)
        self.assertIn("candidate_trajectories", scenario["affects"])

    def test_slow_zone_manifest_records_parameter_sweep_values(self):
        scenario = RUNNER.eval3_slow_zone_manifest(self.args(
            eval3_downstream_slow_zone=True,
            eval3_slow_zone_location="upstream",
            eval3_slow_zone_start_offset=12.0,
            eval3_slow_zone_length=10.0,
            eval3_slow_zone_speed_limit=5.56,
        ))

        self.assertEqual(scenario["start_offset_m"], 12.0)
        self.assertEqual(scenario["location"], "upstream")
        self.assertEqual(scenario["edge_id"], "left")
        self.assertEqual(scenario["lane_id"], "left_0")
        self.assertEqual(scenario["length_m"], 10.0)
        self.assertEqual(scenario["speed_limit_mps"], 5.56)

if __name__ == "__main__":
    unittest.main()

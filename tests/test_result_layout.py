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
            "MCS_FCD_OUTPUT": "/tmp/old-fcd.xml",
            "MCS_CHECKPOINT_DIR": "/tmp/old-checkpoint",
        }

        cleaned = RUNNER.clean_experiment_environment(stale)

        self.assertEqual(cleaned, {"PATH": "/usr/bin"})

    def test_lane_aware_run_explicitly_records_priority_hold_as_off(self):
        self.assertEqual(
            RUNNER.PRIORITY_HOLD_MANIFEST,
            {"mode": "off", "enabled": False})


if __name__ == "__main__":
    unittest.main()

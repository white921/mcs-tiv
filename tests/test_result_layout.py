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
            "conditional_priority_hold": False,
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

    def test_write_json_has_stable_trailing_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            RUNNER.write_json(path, {"status": "completed"})
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '{\n  "status": "completed"\n}\n')


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "outcome_lock_finalizer",
    ROOT / "scripts" / "finalize_intersection_decision_outcome_lock_factorial.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DecisionOutcomeLockFinalizerTest(unittest.TestCase):
    def write_json(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def make_experiment(
        self, parent, name, case, seeds, source, generic_lock,
        accept_lock, reject_lock, speed,
    ):
        root = Path(parent) / name
        root.mkdir(parents=True)
        tasks = [{"case": case, "seed": seed} for seed in seeds]
        self.write_json(root / "experiment-manifest.json", {
            "status": "completed", "completed_simulations": len(tasks),
            "failed_simulations": 0, "tasks": tasks,
        })
        flows = [500, 500, 500] if case == "eval3" else [300] * 4
        for seed in seeds:
            run = root / case / f"seed-{seed}"
            run.mkdir(parents=True)
            fixed = f"fixed-{case}-{seed}"
            self.write_json(run / "manifest.json", {
                "case": case, "seed": seed, "flows_vph": flows,
                "exit_code": 0, "source_unchanged": True,
                "git": {"commit": source, "dirty": False},
                "decision_method": "normalized-deceleration-propagation",
                "deceleration_prediction": {
                    "convex_lambda": 0.95,
                    "decision_lock_s": generic_lock,
                    "decision_lock_accept_s": accept_lock,
                    "decision_lock_reject_s": reject_lock,
                    "lane_metadata_heading_fallback": {"enabled": True},
                },
                "diagnostic_traces_enabled": True,
                "fixed_vehicle_input": {
                    "sha256": fixed, "prefix_sha256": "prefix-" + fixed,
                },
                "checkpoints_written": 5,
                "all_speed_mps": speed,
            })
            self.write_json(run / "evaluation-metrics.json", {
                "groups": {"all": {
                    "samples": 10,
                    "speed_sum": speed * 10,
                    "stop_time_s": 200 - speed * 10,
                    "hard_brake_time_s": 4 - speed / 10,
                }},
                "physical_safety": {
                    "physical_collision_free": True,
                    "unique_collision_episodes": 0,
                },
            })
            self.write_json(run / "deceleration-audit.json", {
                "counts": {
                    "active_attempts": 10,
                    "active_evaluations": 10,
                    "active_unsupported": 0,
                    "active_duplicate_decisions_suppressed": 1,
                },
                "records": [],
            })
            negotiations = (
                '{"event":"started"}\n'
                '{"event":"decision","accept":true}\n'
                '{"event":"decision","accept":false}\n'
                '{"event":"applied"}\n'
                '{"event":"waiting_for_agreement"}\n'
                '{"event":"cancelled"}\n'
                '{"event":"deferred"}\n'
                '{"event":"suppressed"}\n'
            )
            for filename in MODULE.REQUIRED_ARTIFACTS:
                path = run / filename
                if path.exists():
                    continue
                if filename == "negotiations.jsonl":
                    path.write_text(negotiations, encoding="utf-8")
                elif filename.endswith(".json"):
                    self.write_json(path, {})
                else:
                    path.write_bytes(b"")
        return root

    def old_roots(self, parent, prefix, source, generic, accept, reject, speed):
        return [
            self.make_experiment(
                parent, prefix + "-eval3", "eval3", range(13, 18), source,
                generic, accept, reject, speed),
            self.make_experiment(
                parent, prefix + "-eval5", "eval5", range(13, 23), source,
                generic, accept, reject, speed),
        ]

    def arm(self, root, name, source, accept, reject, speed):
        parent = Path(root) / name
        return [
            self.make_experiment(
                parent, "eval3", "eval3", range(13, 18), source,
                1.0, accept, reject, speed),
            self.make_experiment(
                parent, "eval5-a", "eval5", range(13, 18), source,
                1.0, accept, reject, speed),
            self.make_experiment(
                parent, "eval5-b", "eval5", range(18, 23), source,
                1.0, accept, reject, speed),
        ]

    def fixture(self, directory):
        baseline = self.old_roots(
            directory, "baseline", MODULE.BASELINE_SOURCE,
            1.0, 1.0, 1.0, 5.0)
        short = self.old_roots(
            directory, "short", "short-source",
            0.1, 0.1, 0.1, 5.3)
        factorial = Path(directory) / "factorial"
        factorial.mkdir()
        self.arm(
            factorial, "accept-short-reject-long", "factorial-source",
            0.1, 1.0, 5.1)
        self.arm(
            factorial, "accept-long-reject-short", "factorial-source",
            1.0, 0.1, 5.2)
        self.write_json(factorial / "experiment-manifest.json", {
            "status": "completed",
            "source_commit": "factorial-source",
            "automatic_rerun": False,
            "completed_waves": [
                {"results": [{"returncode": 0}] * 3},
                {"results": [{"returncode": 0}] * 3},
            ],
        })
        return baseline, short, factorial

    def test_summary_validates_all_four_cells_and_factorial_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, short, factorial = self.fixture(directory)
            report = MODULE.summarize(
                baseline, short, factorial, MODULE.BASELINE_SOURCE,
                "short-source", "factorial-source")
        self.assertEqual(report["validated_run_count"], 60)
        self.assertEqual(report["validated_new_run_count"], 30)
        condition = report["conditions"]["eval5:300-300-300-300"]
        self.assertEqual(
            condition["best_cell_by_mean_speed"],
            "accept-short-reject-short")
        self.assertAlmostEqual(
            condition["factorial_effects"]["mean_speed_mps"]
            ["shorten_reject_when_accept_long"]["mean"], 0.2)

    def test_rejects_wrong_outcome_specific_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, short, factorial = self.fixture(directory)
            manifest = (
                factorial / "accept-short-reject-long" / "eval3" /
                "eval3" / "seed-13" / "manifest.json")
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["deceleration_prediction"]["decision_lock_accept_s"] = 0.5
            self.write_json(manifest, value)
            with self.assertRaisesRegex(
                    RuntimeError, "Accept decision lock mismatch"):
                MODULE.summarize(
                    baseline, short, factorial, MODULE.BASELINE_SOURCE,
                    "short-source", "factorial-source")

    def test_rejects_incomplete_outer_factorial(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, short, factorial = self.fixture(directory)
            outer = factorial / "experiment-manifest.json"
            value = json.loads(outer.read_text(encoding="utf-8"))
            value["status"] = "running"
            self.write_json(outer, value)
            with self.assertRaisesRegex(RuntimeError, "not completed"):
                MODULE.summarize(
                    baseline, short, factorial, MODULE.BASELINE_SOURCE,
                    "short-source", "factorial-source")


if __name__ == "__main__":
    unittest.main()

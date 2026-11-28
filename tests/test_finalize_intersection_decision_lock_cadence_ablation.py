import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "decision_lock_finalizer",
    ROOT / "scripts" / "finalize_intersection_decision_lock_cadence_ablation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DecisionLockFinalizerTest(unittest.TestCase):
    def write_json(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def make_experiment(self, parent, name, case, seeds, source, lock_s, speed):
        root = Path(parent) / name
        root.mkdir()
        tasks = [{"case": case, "seed": seed} for seed in seeds]
        self.write_json(root / "experiment-manifest.json", {
            "status": "completed", "completed_simulations": len(tasks),
            "failed_simulations": 0, "tasks": tasks,
        })
        flows = [500, 500, 500] if case == "eval3" else [300] * 4
        for seed in seeds:
            run = root / case / f"seed-{seed}"
            run.mkdir(parents=True)
            sha = f"fixed-{case}-{seed}"
            prediction = {
                "convex_lambda": 0.95,
                "lane_metadata_heading_fallback": {"enabled": True},
            }
            if lock_s != 1.0:
                prediction["decision_lock_s"] = lock_s
            self.write_json(run / "manifest.json", {
                "case": case, "seed": seed, "flows_vph": flows,
                "exit_code": 0, "source_unchanged": True,
                "git": {"commit": source, "dirty": False},
                "decision_method": "normalized-deceleration-propagation",
                "deceleration_prediction": prediction,
                "diagnostic_traces_enabled": True,
                "fixed_vehicle_input": {
                    "sha256": sha, "prefix_sha256": "prefix-" + sha},
                "checkpoints_written": 5, "all_speed_mps": speed,
            })
            self.write_json(run / "evaluation-metrics.json", {
                "groups": {"car": {
                    "samples": 10, "speed_sum": speed * 10,
                    "stop_time_s": 100 - speed * 2,
                    "hard_brake_time_s": 2,
                }},
                "physical_safety": {
                    "physical_collision_free": True,
                    "unique_collision_episodes": 0,
                },
            })
            self.write_json(run / "deceleration-audit.json", {
                "counts": {
                    "active_attempts": 10, "active_evaluations": 10,
                    "active_unsupported": 0,
                    "active_duplicate_decisions_suppressed": 1,
                },
            })
            for filename in MODULE.REQUIRED_ARTIFACTS:
                path = run / filename
                if path.exists():
                    continue
                if filename == "negotiations.jsonl":
                    path.write_text(
                        '{"event":"suppressed"}\n'
                        '{"event":"decision"}\n'
                        '{"event":"cancelled"}\n', encoding="utf-8")
                elif filename.endswith(".json"):
                    self.write_json(path, {})
                else:
                    path.write_bytes(b"")
        return root

    def roots(self, directory, prefix, source, lock_s, speed):
        return [
            self.make_experiment(
                directory, prefix + "-eval3", "eval3", range(13, 18),
                source, lock_s, speed),
            self.make_experiment(
                directory, prefix + "-eval5", "eval5", range(13, 23),
                source, lock_s, speed),
        ]

    def test_summary_validates_pairs_and_detects_improvement(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = self.roots(
                directory, "before", MODULE.BASELINE_SOURCE, 1.0, 5.0)
            short = self.roots(
                directory, "after", "short-source", 0.1, 5.2)
            report = MODULE.summarize(
                baseline, short, MODULE.BASELINE_SOURCE, "short-source")
        self.assertEqual(report["validated_baseline_run_count"], 15)
        self.assertEqual(report["validated_short_lock_run_count"], 15)
        self.assertTrue(report["cadence_hypothesis"]["supported"])

    def test_rejects_wrong_lock_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = self.roots(
                directory, "before", MODULE.BASELINE_SOURCE, 1.0, 5.0)
            short = self.roots(
                directory, "after", "short-source", 0.1, 5.2)
            manifest = short[0] / "eval3" / "seed-13" / "manifest.json"
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["deceleration_prediction"]["decision_lock_s"] = 0.5
            self.write_json(manifest, value)
            with self.assertRaisesRegex(RuntimeError, "decision lock mismatch"):
                MODULE.summarize(
                    baseline, short, MODULE.BASELINE_SOURCE, "short-source")


if __name__ == "__main__":
    unittest.main()

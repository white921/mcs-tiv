import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fallback_finalizer",
    ROOT / "scripts" / "finalize_intersection_lane_heading_fallback_ablation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FallbackAblationFinalizerTest(unittest.TestCase):
    def write_json(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def make_experiment(self, parent, name, case, seeds, source, fallback,
                        unsupported, speed):
        root = Path(parent) / name
        root.mkdir()
        tasks = [{"case": case, "seed": seed} for seed in seeds]
        self.write_json(root / "experiment-manifest.json", {
            "status": "completed",
            "completed_simulations": len(tasks),
            "failed_simulations": 0,
            "tasks": tasks,
        })
        flows = [500, 500, 500] if case == "eval3" else [300] * 4
        for seed in seeds:
            run = root / case / f"seed-{seed}"
            run.mkdir(parents=True)
            sha = f"fixed-{case}-{seed}"
            self.write_json(run / "manifest.json", {
                "case": case,
                "seed": seed,
                "flows_vph": flows,
                "exit_code": 0,
                "source_unchanged": True,
                "git": {"commit": source, "dirty": False},
                "decision_method": "normalized-deceleration-propagation",
                "deceleration_prediction": ({
                    "convex_lambda": 0.95,
                    "lane_metadata_heading_fallback": {"enabled": True},
                } if fallback else {"convex_lambda": 0.95}),
                "diagnostic_traces_enabled": True,
                "fixed_vehicle_input": {
                    "sha256": sha, "prefix_sha256": "prefix-" + sha},
                "checkpoints_written": 5,
                "all_speed_mps": speed,
            })
            self.write_json(run / "evaluation-metrics.json", {
                "groups": {"car": {
                    "samples": 10, "speed_sum": speed * 10,
                    "stop_time_s": 100 - speed,
                    "hard_brake_time_s": 2,
                }},
                "physical_safety": {
                    "physical_collision_free": True,
                    "unique_collision_episodes": 0,
                },
            })
            self.write_json(run / "deceleration-audit.json", {
                "counts": {
                    "active_attempts": 100,
                    "active_evaluations": 100 - unsupported,
                    "active_unsupported": unsupported,
                },
            })
            for filename in MODULE.REQUIRED_ARTIFACTS:
                path = run / filename
                if path.exists():
                    continue
                if filename.endswith(".json"):
                    self.write_json(path, {})
                else:
                    path.write_bytes(b"")
        return root

    def make_roots(self, directory, source, fallback, unsupported, speed):
        label = "after" if fallback else "before"
        return [
            self.make_experiment(
                directory, label + "-eval3", "eval3", range(13, 18),
                source, fallback, unsupported, speed),
            self.make_experiment(
                directory, label + "-eval5", "eval5", range(13, 23),
                source, fallback, unsupported, speed),
        ]

    def test_summary_validates_pairs_and_passes_advancement_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = self.make_roots(
                directory, MODULE.BASELINE_SOURCE, False, 10, 5.0)
            ablation = self.make_roots(
                directory, MODULE.ABLATION_SOURCE, True, 1, 5.2)
            report = MODULE.summarize(
                baseline, ablation, MODULE.BASELINE_SOURCE,
                MODULE.ABLATION_SOURCE)
        self.assertEqual(report["validated_baseline_run_count"], 15)
        self.assertEqual(report["validated_ablation_run_count"], 15)
        self.assertTrue(report["advancement_gate"][
            "eligible_for_fresh_seed_validation"])
        self.assertAlmostEqual(
            report["conditions"]["eval3:500-500-500"]
            ["unsupported_relative_reduction"], 0.9)

    def test_summary_rejects_fixed_input_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = self.make_roots(
                directory, MODULE.BASELINE_SOURCE, False, 10, 5.0)
            ablation = self.make_roots(
                directory, MODULE.ABLATION_SOURCE, True, 1, 5.2)
            manifest = ablation[0] / "eval3" / "seed-13" / "manifest.json"
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["fixed_vehicle_input"]["sha256"] = "different"
            self.write_json(manifest, value)
            with self.assertRaisesRegex(RuntimeError, "fixed input mismatch"):
                MODULE.summarize(
                    baseline, ablation, MODULE.BASELINE_SOURCE,
                    MODULE.ABLATION_SOURCE)


if __name__ == "__main__":
    unittest.main()

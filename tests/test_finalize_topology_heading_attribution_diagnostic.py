import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "finalize_heading",
    ROOT / "scripts" / "finalize_topology_heading_attribution_diagnostic.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FinalizeTopologyHeadingAttributionDiagnosticTest(unittest.TestCase):
    def write_json(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def make_experiment(self, root):
        run = root / "eval5" / "seed-13"
        run.mkdir(parents=True)
        self.write_json(root / "experiment-manifest.json", {
            "status": "completed", "completed_simulations": 1,
            "failed_simulations": 0,
            "tasks": [{"case": "eval5", "seed": 13}],
        })
        self.write_json(run / "manifest.json", {
            "experiment_id": root.name, "case": "eval5", "seed": 13,
            "flows_vph": [300, 300, 300, 300], "exit_code": 0,
            "source_unchanged": True,
            "git": {"commit": MODULE.EXPECTED_SOURCE, "dirty": False},
            "decision_method": "normalized-deceleration-propagation",
            "deceleration_prediction": {"convex_lambda": 0.95},
            "diagnostic_traces_enabled": True, "checkpoints_written": 5,
            "fixed_vehicle_input": {"sha256": "a", "prefix_sha256": "b"},
            "all_speed_mps": 7.0,
        })
        self.write_json(run / "evaluation-metrics.json", {
            "physical_safety": {"physical_collision_free": True,
                                "unique_collision_episodes": 0},
        })
        self.write_json(run / "deceleration-audit.json", {
            "counts": {"active_attempts": 4, "active_evaluations": 3,
                       "active_unsupported": 1},
            "records": [{
                "status": "unsupported",
                "reason": "trajectory has no usable heading or yaw",
                "unsupported_details": {
                    "counterfactual_case": "reject",
                    "heading_path": {
                        "path_type": "planned", "lane_id": "east_0",
                        "lane_position": 12.0,
                        "distinct_position_count": 1, "finite_yaw_count": 0,
                    },
                },
            }],
        })
        self.write_json(run / "tiv-audit.json", {})
        for name in MODULE.REQUIRED_AUDITS:
            path = run / name
            if path.exists():
                continue
            path.write_bytes(b"" if name.endswith((".jsonl", ".gz")) else b"{}")
        return run

    def test_validates_and_attributes_stationary_path_without_yaw(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "experiment"
            root.mkdir()
            self.make_experiment(root)
            report = MODULE.summarize([root], MODULE.EXPECTED_SOURCE)

        condition = report["conditions"]["eval5:300-300-300-300"]
        self.assertEqual(report["validated_run_count"], 1)
        self.assertEqual(condition["active_unsupported"], 1)
        self.assertEqual(condition["stationary_without_yaw"], 1)
        self.assertEqual(condition["lane_position_present"], 1)
        self.assertEqual(condition["counterfactual_case"], {"reject": 1})
        self.assertEqual(condition["retained_detail_coverage"], 1.0)

    def test_rejects_incomplete_experiment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "experiment"
            root.mkdir()
            self.write_json(root / "experiment-manifest.json", {
                "status": "running", "tasks": [],
            })
            with self.assertRaisesRegex(RuntimeError, "not completed"):
                MODULE.summarize([root], MODULE.EXPECTED_SOURCE)


if __name__ == "__main__":
    unittest.main()

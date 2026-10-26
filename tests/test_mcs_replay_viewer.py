import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mcs_replay_viewer import (
    FrameStore,
    ReplayCatalog,
    display_method,
    find_trace,
    find_network,
    logical_experiment_id,
    parse_network,
    physical_experiment_id,
)


class ReplayViewerTests(unittest.TestCase):
    def test_frame_store_indexes_uncompressed_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vehicle-states.jsonl"
            records = [
                {"sim_time": 0.1, "vehicles": []},
                {"sim_time": 0.2, "vehicles": [{"vehicle_id": "1"}]},
            ]
            path.write_text("".join(json.dumps(record) + "\n" for record in records))
            store = FrameStore(path)
            self.assertEqual(store.times, [0.1, 0.2])
            self.assertEqual(store.get(1)["vehicles"][0]["vehicle_id"], "1")

    def test_find_trace_prefers_full_stitched_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            partial = run / "vehicle-states.jsonl"
            full = run / "vehicle-states-full.jsonl.gz"
            partial.write_text("partial")
            full.write_text("full")
            self.assertEqual(find_trace(run, "vehicle-states.jsonl"), full)

    def test_parse_network_returns_lane_shapes_and_bounds(self):
        network = parse_network(ROOT / "junction" / "junction_three.net.xml")
        self.assertEqual(network["bounds"], [0.0, -150.0, 300.0, 150.0])
        self.assertTrue(any(lane["id"] == "bottom_0" for lane in network["lanes"]))
        self.assertTrue(all(len(lane["shape"]) >= 2 for lane in network["lanes"]))

    def test_find_network_uses_case_specific_network(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            junction = run / "source" / "junction"
            merge = run / "source" / "merge"
            junction.mkdir(parents=True)
            merge.mkdir(parents=True)
            for name in ("junction_three.net.xml", "junction_four.net.xml"):
                shutil.copy(ROOT / "junction" / name, junction / name)
            shutil.copy(ROOT / "merge" / "threeLane.net.xml",
                        merge / "threeLane.net.xml")
            self.assertEqual(find_network(run, "eval3").name,
                             "junction_three.net.xml")
            self.assertEqual(find_network(run, "eval5").name,
                             "junction_four.net.xml")
            self.assertEqual(find_network(run, "eval7").name,
                             "threeLane.net.xml")

    def test_catalog_groups_experiment_eval_and_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = root / "20261026__proposal"
            (experiment / "summary.json").parent.mkdir(parents=True)
            (experiment / "summary.json").write_text("{}")
            for case, seed in (("eval3", 1), ("eval3", 2), ("eval7", 7)):
                run = experiment / case / f"seed-{seed}"
                run.mkdir(parents=True)
                (run / "manifest.json").write_text(json.dumps({
                    "case": case, "seed": seed, "exit_code": 0,
                    "started_epoch": 1, "decision_method": "proposal",
                    "input_duration": 600,
                }))
                (run / "vehicle-states.jsonl").write_text(
                    json.dumps({"sim_time": 0.1, "vehicles": []}) + "\n")
            catalog = ReplayCatalog(root).metadata()
            self.assertEqual(len(catalog["entries"]), 3)
            self.assertEqual(
                {entry["experiment_id"] for entry in catalog["entries"]},
                {"20261026__proposal"})
            self.assertEqual(
                {(entry["case"], int(entry["seed"]))
                 for entry in catalog["entries"]},
                {("eval3", 1), ("eval3", 2), ("eval7", 7)})

    def test_display_method_uses_short_japanese_labels(self):
        self.assertEqual(
            display_method("priority-hold-gated180", "deceleration-propagation"),
            "条件付き合意保持")
        self.assertEqual(
            display_method("formal", "deceleration-propagation"),
            "提案手法")
        self.assertEqual(display_method("formal", "thesis-tiv"), "山下手法")

    def test_recovery_entries_join_the_original_experiment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_name = "baseline-20261026"
            original = root / original_name / "eval3" / "seed-1"
            original.mkdir(parents=True)
            (original.parent.parent / "summary.json").write_text("{}")
            base_manifest = {
                "case": "eval3", "seed": 1, "exit_code": 0,
                "started_epoch": 1, "decision_method": "deceleration-propagation",
                "stop_time": 300,
            }
            (original / "manifest.json").write_text(json.dumps(base_manifest))
            (original / "vehicle-states.jsonl").write_text(
                json.dumps({"sim_time": 0.1, "vehicles": []}) + "\n")

            recovered = root / "recovery-seed2" / "eval3" / "seed-2"
            recovered.mkdir(parents=True)
            (recovered.parent.parent / "summary.json").write_text("{}")
            recovery_manifest = {
                **base_manifest,
                "seed": 2,
                "started_epoch": 2,
                "checkpointing": {
                    "resume_from": (
                        f"/remote/repo/results/runs/{original_name}/"
                        "eval3/seed-2/checkpoints/t0000240.0")
                },
            }
            (recovered / "manifest.json").write_text(json.dumps(recovery_manifest))
            (recovered / "vehicle-states.jsonl").write_text(
                json.dumps({"sim_time": 240.1, "vehicles": []}) + "\n")

            entries = ReplayCatalog(root).metadata()["entries"]
            self.assertEqual({entry["experiment_id"] for entry in entries},
                             {original_name})
            self.assertEqual({int(entry["seed"]) for entry in entries}, {1, 2})
            self.assertEqual(len({entry["experiment_label"] for entry in entries}), 1)
            self.assertTrue(entries[0]["experiment_label"].endswith("復旧統合"))

    def test_logical_experiment_id_falls_back_for_non_checkpoint_runs(self):
        self.assertEqual(logical_experiment_id({}, "run-a"), "run-a")

    def test_modern_results_run_uses_directory_name_as_experiment_id(self):
        root = Path("/repo/results")
        experiment = root / "runs" / "baseline-20261026"
        self.assertEqual(
            physical_experiment_id(experiment, root), "baseline-20261026")

    def test_catalog_numbers_duplicate_display_labels_by_experiment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for experiment_name in ("run-a", "run-b"):
                run = root / experiment_name / "eval3" / "seed-1"
                run.mkdir(parents=True)
                (run.parent.parent / "summary.json").write_text("{}")
                (run / "manifest.json").write_text(json.dumps({
                    "case": "eval3", "seed": 1, "exit_code": 0,
                    "started_epoch": 1, "decision_method": "thesis-tiv",
                    "stop_time": 600,
                }))
                (run / "vehicle-states.jsonl").write_text(
                    json.dumps({"sim_time": 0.1, "vehicles": []}) + "\n")
            labels = {
                entry["experiment_label"]
                for entry in ReplayCatalog(root).metadata()["entries"]
            }
            self.assertEqual(len(labels), 2)
            self.assertTrue(any(label.endswith("再実行1") for label in labels))
            self.assertTrue(any(label.endswith("再実行2") for label in labels))


if __name__ == "__main__":
    unittest.main()

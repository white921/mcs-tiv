import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
sys.path.insert(0, str(ROOT / "scripts"))

from fixed_vehicle_inputs import load_fixed_vehicle_input
from generate_eval35_formal_inputs import (
    CONDITIONS,
    GENERATION_PYTHON,
    SEEDS,
    expected_files,
)
from run_thesis_batch import fixed_input_details, selected_flows


class Eval35FormalInputTests(unittest.TestCase):
    def test_committed_files_match_generator_and_paper_conditions(self):
        root = ROOT / "fixed_inputs" / "thesis" / "eval35-paper-comparison"
        expected_paths = {path for path, _ in expected_files(root)}
        self.assertEqual(set(root.glob("*/*.jsonl")), expected_paths)
        for path, expected in expected_files(root):
            with self.subTest(path=path):
                self.assertEqual(path.read_text(encoding="utf-8"), expected)
                condition = path.parent.name
                case, flows = CONDITIONS[condition]
                seed = int(path.stem.split("-")[1])
                schedule = load_fixed_vehicle_input(
                    path,
                    expected_case=case,
                    expected_seed=seed,
                    expected_flows_vph=flows,
                    expected_bus_share=0.25,
                    prefix_duration_s=600,
                )
                self.assertEqual(
                    schedule.metadata["generated_with_python"], GENERATION_PYTHON
                )
                expected_count = sum(int(flow / 6) for flow in flows.values())
                self.assertEqual(len(schedule.events), expected_count)
                self.assertEqual(
                    sum(event["vehicle_type"] == "Bus" for event in schedule.events),
                    int(expected_count * 0.25 + 0.5),
                )

    def test_seed_set_is_preregistered_and_unused_by_legacy_defaults(self):
        self.assertEqual(SEEDS, tuple(range(13, 23)))

    def test_runner_selects_overridden_junction_flows_and_input_hash(self):
        args = SimpleNamespace(case_flows=[500, 500, 500], eval7_flows=None)
        self.assertEqual(selected_flows("eval3", args), ["500", "500", "500"])
        template = (
            "fixed_inputs/thesis/eval35-paper-comparison/"
            "eval3-500/seed-{seed}.jsonl"
        )
        details = fixed_input_details(
            "eval3",
            13,
            600,
            "fixed",
            flows=(500, 500, 500),
            relative_path_override=template,
        )
        path = ROOT / details["relative_path"]
        self.assertEqual(details["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(details["prefix_event_count"], 249)


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import unittest


RUNNER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_thesis_batch.py"
SPEC = importlib.util.spec_from_file_location("run_thesis_batch", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class DecisionMethodSelectionTests(unittest.TestCase):
    def test_documented_eval7_selects_tivtep(self):
        self.assertEqual(
            RUNNER.selected_decision_method(
                RUNNER.CASES["eval7"], "documented"),
            ("tivtep", "7"),
        )

    def test_utf_selects_alpha_five(self):
        self.assertEqual(
            RUNNER.selected_decision_method(RUNNER.CASES["eval7"], "utf"),
            ("utf", "5"),
        )

    def test_tivte_selects_alpha_six(self):
        self.assertEqual(
            RUNNER.selected_decision_method(RUNNER.CASES["eval7"], "tivte"),
            ("tivte", "6"),
        )


if __name__ == "__main__":
    unittest.main()

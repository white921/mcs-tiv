import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "func"))

import thesis_baselines
import thesis_scenarios
from run_yamashita_evaluations import build_command
from thesis_evaluations import EVALUATIONS


class ThesisBaselineTests(unittest.TestCase):
    def test_act_retains_priority_for_horizontal_road_and_straight(self):
        for route in ("LR", "LB", "LT", "RL", "RB", "RT", "BT", "TB"):
            self.assertEqual(thesis_baselines.act_utility(route), 0.0)
        for route in ("BR", "BL", "TR", "TL"):
            self.assertEqual(thesis_baselines.act_utility(route), 1.0)

    def test_spd_accepts_the_exact_threshold(self):
        self.assertTrue(thesis_baselines.accepts_utility(3, 0.0))
        self.assertTrue(thesis_baselines.accepts_utility(4, 0.0))
        self.assertFalse(thesis_baselines.accepts_utility(3, -1e-9))
        self.assertFalse(thesis_baselines.accepts_utility(5, 0.0))


class ThesisScenarioTests(unittest.TestCase):
    @staticmethod
    def first(values):
        return values[0]

    def test_eval1_forces_a_and_c_straight(self):
        self.assertEqual(
            thesis_scenarios.choose_t_junction_route("left", "eval1", self.first),
            "LR",
        )
        self.assertEqual(
            thesis_scenarios.choose_t_junction_route("right", "eval1", self.first),
            "RL",
        )
        self.assertEqual(
            thesis_scenarios.choose_t_junction_route("bottom", "eval1", self.first),
            "BR",
        )

    def test_unrestricted_mode_keeps_two_destinations_per_approach(self):
        for approach in ("left", "bottom", "right"):
            routes = thesis_scenarios.T_JUNCTION_RANDOM_ROUTES[approach]
            self.assertEqual(len(routes), 2)


class ThesisEvaluationMatrixTests(unittest.TestCase):
    def test_eval1_and_eval2_conditions(self):
        eval1 = EVALUATIONS["eval1"]
        self.assertEqual(eval1.bus_share, 0.0)
        self.assertEqual(eval1.route_mode, "eval1")
        self.assertEqual(eval1.methods, ("ALW", "ACT", "SPD40", "UTF", "TIVte"))
        self.assertEqual(eval1.conditions[2].inflows, (600, 300, 600))

        eval2 = EVALUATIONS["eval2"]
        self.assertEqual(eval2.bus_share, 0.0)
        self.assertEqual(eval2.route_mode, "random")
        self.assertIn("SPD20", eval2.methods)
        self.assertEqual(
            tuple(condition.inflows for condition in eval2.conditions),
            ((400, 400, 400), (500, 500, 500), (600, 600, 600)),
        )

    def test_eval3_includes_defined_600_condition(self):
        self.assertEqual(EVALUATIONS["eval3"].conditions[-1].inflows, (600, 600, 600))
        self.assertTrue(all(value is None for value in EVALUATIONS["eval3"].conditions[-1].references))

    def test_documented_default_seed_sets(self):
        self.assertEqual(EVALUATIONS["eval4"].default_seeds, (1, 3, 5, 6, 7))
        self.assertEqual(EVALUATIONS["eval6"].default_seeds, (1, 2, 3, 6, 8))
        self.assertEqual(EVALUATIONS["eval7"].default_seeds, (1, 2, 3, 7, 11))

    def test_eval1_command_contains_paper_switches(self):
        evaluation = EVALUATIONS["eval1"]
        command = build_command(
            evaluation,
            "TIVte",
            (600, 300, 600),
            2,
            600,
            "fixed",
        )
        self.assertIn("--bus-share", command)
        self.assertEqual(command[command.index("--bus-share") + 1], "0.0")
        self.assertEqual(command[command.index("--route-mode") + 1], "eval1")
        self.assertIn("--no-save", command)


if __name__ == "__main__":
    unittest.main()

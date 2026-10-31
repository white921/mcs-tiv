import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import plan_decision_oracle_corpus as planner
import run_decision_oracle
import run_decision_oracle_corpus as corpus


class DecisionOracleCorpusTests(unittest.TestCase):
    def test_selection_keeps_natural_ordinal_and_deduplicates_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "negotiations.jsonl"
            records = [
                {"event": "started", "sim_time": 1.0},
                {"event": "decision", "sim_time": 1.1,
                 "reason": "no_feasible_alternative",
                 "receiver_id": "9", "sender_id": "8",
                 "desired_path_id": "8_1"},
                {"event": "decision", "sim_time": 2.1,
                 "reason": "thesis-tiv-fallback",
                 "receiver_id": "2", "sender_id": "1",
                 "desired_path_id": "1_1"},
                {"event": "decision", "sim_time": 2.0,
                 "reason": "thesis-tiv-fallback",
                 "receiver_id": "2", "sender_id": "1",
                 "desired_path_id": "1_1"},
                {"event": "decision", "sim_time": 3.0,
                 "reason": "deceleration-propagation",
                 "receiver_id": "4", "sender_id": "3",
                 "desired_path_id": "3_1"},
            ]
            trace.write_text("".join(json.dumps(item) + "\n" for item in records))
            selected = planner.selected_events(trace, 2)
            self.assertEqual([item["ordinal"] for item in selected], [1, 3])
            self.assertEqual(selected[1]["receiver_id"], "4")

    def test_macro_regret_equal_weights_cases(self):
        summaries = {
            "eval3": {"policies": {"proposal": {"mean_regret_m": 1.0}}},
            "eval5": {"policies": {"proposal": {"mean_regret_m": 2.0}}},
            "eval7": {"policies": {"proposal": {"mean_regret_m": 6.0}}},
        }
        self.assertEqual(
            corpus.macro_case_mean_regret(summaries)["proposal"], 3.0)

    def test_scenario_command_disables_statistics_for_every_case(self):
        for case in ("eval3", "eval5", "eval7"):
            args = NS(
                case=case, seed=1, duration=300.0,
                python="python", origin_policy="yamashita")
            command, _ = run_decision_oracle.scenario_command(
                args, ROOT, 10.0)
            self.assertIn("--no-save", command)

    def test_proposal_origin_replay_uses_explicit_loss_lambda(self):
        args = NS(
            sumo_home=Path("/tmp/sumo"), origin_policy="proposal",
            deceleration_loss_lambda=2.0)

        with mock.patch.dict(os.environ, {}, clear=True):
            env = run_decision_oracle.common_env(args, ROOT)

        self.assertEqual(env["MCS_DECELERATION_LOSS_LAMBDA"], "2.0")

    def test_boundary_identity_uses_boundary_request_field_names(self):
        request = {
            "receiver": "15",
            "sender": "9",
            "desired_path_id": "9_42",
        }
        run_decision_oracle.validate_event_identity(request, {
            "receiver_id": "15",
            "sender_id": "9",
            "desired_path_id": "9_42",
        })
        with self.assertRaisesRegex(RuntimeError, "receiver_id"):
            run_decision_oracle.validate_event_identity(request, {
                "receiver_id": "16",
                "sender_id": "9",
                "desired_path_id": "9_42",
            })


if __name__ == "__main__":
    unittest.main()

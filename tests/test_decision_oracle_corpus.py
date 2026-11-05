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

    def test_time_stratified_selection_is_deterministic_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "negotiations.jsonl"
            records = [
                {"event": "decision", "sim_time": float(moment),
                 "reason": "deceleration-propagation",
                 "receiver_id": str(moment), "sender_id": "1",
                 "desired_path_id": f"1_{moment}"}
                for moment in range(95, 116)
            ]
            trace.write_text("".join(json.dumps(item) + "\n" for item in records))
            first = planner.selected_events(
                trace, 4, time_start_s=100.0, time_end_s=110.0,
                sampling_seed=20261103, selection_key="proposal:eval3:13")
            second = planner.selected_events(
                trace, 4, time_start_s=100.0, time_end_s=110.0,
                sampling_seed=20261103, selection_key="proposal:eval3:13")
            self.assertEqual(first, second)
            self.assertEqual(len(first), 4)
            self.assertTrue(all(100.0 <= item["sim_time_s"] < 110.0
                                for item in first))
            self.assertEqual(
                [item["ordinal"] for item in first],
                sorted(item["ordinal"] for item in first))

    def test_time_stratified_selection_rejects_short_window(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "negotiations.jsonl"
            records = [
                {"event": "decision", "sim_time": float(moment),
                 "reason": "thesis-tiv-fallback",
                 "receiver_id": str(moment), "sender_id": "1",
                 "desired_path_id": f"1_{moment}"}
                for moment in (120, 121, 122)
            ]
            trace.write_text("".join(json.dumps(item) + "\n" for item in records))
            with self.assertRaisesRegex(ValueError, "only 3 unique decisions"):
                planner.selected_events(
                    trace, 4, time_start_s=120.0, time_end_s=180.0,
                    sampling_seed=20261103, selection_key="yamashita:eval5:18")

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

    def test_corpus_command_passes_explicit_cohort_mode(self):
        args = NS(
            python=Path("/tmp/python"), sumo_home=Path("/tmp/sumo"),
            duration=300.0, deceleration_loss_lambda=2.0,
            cohort_mode="actors-followers", checkpoint_roots={
                "yamashita": None, "proposal": None})
        event = {
            "case": "eval3", "origin_policy": "proposal", "seed": 13,
            "ordinal": 1, "sim_time_s": 100.0,
            "receiver_id": "1", "sender_id": "2",
            "desired_path_id": "2_3",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runner-logs").mkdir()
            with mock.patch.object(corpus.subprocess, "run") as run:
                run.return_value.returncode = 1
                corpus.run_event(
                    args, root / "source", root / "git.json",
                    root, 1, event)
            command = run.call_args.args[0]
        self.assertIn("--cohort-mode", command)
        self.assertEqual(
            command[command.index("--cohort-mode") + 1], "actors-followers")

    def test_corpus_chooses_latest_complete_checkpoint_before_event(self):
        event = {
            "case": "eval3", "origin_policy": "proposal", "seed": 13,
            "ordinal": 1, "sim_time_s": 220.0,
            "receiver_id": "1", "sender_id": "2",
            "desired_path_id": "2_3",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_root = root / "eval3" / "seed-13"
            run_root.mkdir(parents=True)
            (run_root / "manifest.json").write_text(json.dumps({
                "exit_code": 0, "source_unchanged": True,
            }))
            checkpoint_root = run_root / "checkpoints"
            for moment in (60.0, 120.0, 180.0, 240.0):
                path = checkpoint_root / f"t{moment:09.1f}"
                path.mkdir(parents=True)
                (path / "checkpoint.json").write_text(json.dumps({
                    "schema_version": 1, "case": "eval3", "seed": 13,
                    "simulation_time_s": moment,
                }))
                (path / "mcs-state.pkl").touch()
                (path / "sumo-state.xml.gz").touch()
            args = NS(checkpoint_roots={"yamashita": None, "proposal": root})
            selected = corpus.capture_checkpoint_for_event(args, event)
            self.assertEqual(selected.name, "t0000180.0")

    def test_event_runner_passes_capture_resume_checkpoint(self):
        args = NS(
            python=Path("/tmp/python"), sumo_home=Path("/tmp/sumo"),
            duration=300.0, deceleration_loss_lambda=2.0,
            cohort_mode="actors-followers")
        event = {
            "case": "eval3", "origin_policy": "proposal", "seed": 13,
            "ordinal": 1, "sim_time_s": 100.0,
            "receiver_id": "1", "sender_id": "2",
            "desired_path_id": "2_3",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / "checkpoint"
            checkpoint.mkdir()
            (root / "runner-logs").mkdir()
            with mock.patch.object(corpus.subprocess, "run") as run:
                run.return_value.returncode = 1
                corpus.run_event(
                    args, root / "source", root / "git.json",
                    root, 1, event, checkpoint)
            command = run.call_args.args[0]
        self.assertIn("--capture-resume-checkpoint", command)
        self.assertEqual(
            command[command.index("--capture-resume-checkpoint") + 1],
            str(checkpoint))

    def test_corpus_resolves_exact_event_checkpoint(self):
        event = {
            "case": "eval7", "origin_policy": "proposal", "seed": 23,
            "ordinal": 9, "sim_time_s": 100.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = (root / "eval7" / "proposal" / "seed-23"
                          / "checkpoints" / "t0000099.9")
            checkpoint.mkdir(parents=True)
            (checkpoint / "checkpoint.json").write_text(json.dumps({
                "schema_version": 1, "case": "eval7", "seed": 23,
                "simulation_time_s": 99.9,
            }))
            (checkpoint / "mcs-state.pkl").touch()
            (checkpoint / "sumo-state.xml.gz").touch()
            self.assertEqual(
                corpus.exact_checkpoint_for_event(root, event), checkpoint)

    def test_event_runner_passes_exact_checkpoint(self):
        args = NS(
            python=Path("/tmp/python"), sumo_home=Path("/tmp/sumo"),
            duration=300.0, deceleration_loss_lambda=2.0,
            cohort_mode="actors-followers")
        event = {
            "case": "eval7", "origin_policy": "proposal", "seed": 23,
            "ordinal": 1, "sim_time_s": 100.0,
            "receiver_id": "1", "sender_id": "2",
            "desired_path_id": "2_3",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / "checkpoint"
            checkpoint.mkdir()
            (root / "runner-logs").mkdir()
            with mock.patch.object(corpus.subprocess, "run") as run:
                run.return_value.returncode = 1
                corpus.run_event(
                    args, root / "source", root / "git.json",
                    root, 1, event, None, checkpoint)
            command = run.call_args.args[0]
        self.assertIn("--exact-checkpoint", command)
        self.assertEqual(
            command[command.index("--exact-checkpoint") + 1],
            str(checkpoint))

    def test_eval7_checkpoint_reuse_is_excluded_after_failed_equivalence(self):
        args = NS(checkpoint_roots={
            "yamashita": Path("/unused"), "proposal": Path("/unused")})
        for origin in ("yamashita", "proposal"):
            event = {
                "case": "eval7", "origin_policy": origin, "seed": 13,
                "ordinal": 1, "sim_time_s": 200.0,
            }
            self.assertIsNone(
                corpus.capture_checkpoint_for_event(args, event))

    def test_capture_resume_metadata_rejects_wrong_seed(self):
        args = NS(case="eval3", seed=14)
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory)
            (checkpoint / "checkpoint.json").write_text(json.dumps({
                "schema_version": 1, "case": "eval3", "seed": 13,
                "simulation_time_s": 60.0,
            }))
            (checkpoint / "mcs-state.pkl").touch()
            (checkpoint / "sumo-state.xml.gz").touch()
            with self.assertRaisesRegex(ValueError, "seed mismatch"):
                run_decision_oracle.capture_resume_metadata(
                    checkpoint, args, 99.9)

    def test_exact_checkpoint_metadata_requires_exact_time(self):
        args = NS(case="eval3", seed=23)
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory)
            (checkpoint / "checkpoint.json").write_text(json.dumps({
                "schema_version": 1, "case": "eval3", "seed": 23,
                "simulation_time_s": 99.8,
            }))
            (checkpoint / "mcs-state.pkl").touch()
            (checkpoint / "sumo-state.xml.gz").touch()
            with self.assertRaisesRegex(ValueError, "time mismatch"):
                run_decision_oracle.exact_checkpoint_metadata(
                    checkpoint, args, 99.9)

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

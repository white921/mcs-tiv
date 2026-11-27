import importlib.util
from pathlib import Path
import json
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_universal_lambda095_holdout.py"
SPEC = importlib.util.spec_from_file_location("lambda095_holdout_queue", SCRIPT)
QUEUE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUEUE)


class UniversalLambda095HoldoutQueueTests(unittest.TestCase):
    def test_queue_has_sixty_tasks_in_condition_method_seed_order(self):
        tasks = QUEUE.build_ordered_tasks()
        self.assertEqual(len(tasks), 60)
        self.assertEqual(
            tasks[:12],
            [
                *(('eval3-500', 'proposal', seed) for seed in range(23, 33)),
                ('eval3-500', 'yamashita', 23),
                ('eval3-500', 'yamashita', 24),
            ],
        )
        self.assertTrue(
            all(condition == "eval3-500" for condition, _, _ in tasks[:20])
        )
        self.assertTrue(
            all(condition == "eval5-300" for condition, _, _ in tasks[20:40])
        )
        self.assertTrue(
            all(condition == "eval7-1000" for condition, _, _ in tasks[40:])
        )

    def test_initial_slots_finish_proposal_cohort_before_baseline(self):
        tasks = QUEUE.build_ordered_tasks()[:15]
        self.assertEqual(
            sum(method == "proposal" for _, method, _ in tasks), 10
        )
        self.assertEqual(
            sum(method == "yamashita" for _, method, _ in tasks), 5
        )

    def test_fixed_input_is_shared_by_methods(self):
        for condition in QUEUE.CONDITION_ORDER:
            template = QUEUE.fixed_input_template(condition)
            self.assertIn(condition, template)
            self.assertTrue(template.endswith("seed-{seed}.jsonl"))

    def test_output_names_identify_formal_context(self):
        name = QUEUE.output_name("eval7-1000", "proposal", "20261127")
        self.assertEqual(
            name,
            "universal-lambda095-holdout-eval7-1000-proposal-"
            "seeds23-32-600s-20261127",
        )

    def test_external_runs_reduce_only_initial_managed_capacity(self):
        self.assertEqual(QUEUE.available_capacity(15, 4, 0), 11)
        self.assertEqual(QUEUE.available_capacity(15, 4, 11), 0)
        self.assertEqual(QUEUE.available_capacity(15, 0, 11), 4)

    def test_external_process_classification_uses_worktree_path(self):
        root = Path("/research/mcs-tiv-universal-lambda095-holdout")
        commands = [
            "101 sumo --fcd-output /research/mcs-tiv-diagnostic-artifacts/a.xml.gz",
            "102 sumo --fcd-output /research/mcs-tiv-universal-lambda095-holdout/results/a.xml.gz",
        ]
        self.assertEqual(
            QUEUE.external_sumo_commands(root, commands),
            [commands[0]],
        )

    def test_version_probe_is_not_counted_as_a_simulation(self):
        self.assertFalse(
            QUEUE.is_simulation_sumo_command("101 /opt/sumo/bin/sumo --version")
        )
        self.assertTrue(
            QUEUE.is_simulation_sumo_command(
                "102 /opt/sumo/bin/sumo -c merge.sumocfg --remote-port 10001"
            )
        )

    def test_process_parser_ignores_dead_processes_and_version_probes(self):
        output = "\n".join(
            (
                "101 Z [sumo] <defunct>",
                "102 S /opt/sumo/bin/sumo --version",
                "103 R /opt/sumo/bin/sumo -c merge.sumocfg --remote-port 10001",
                "104 X [sumo]",
                "105 S [sumo]",
            )
        )
        self.assertEqual(
            QUEUE.parse_sumo_process_output(output),
            ["103 /opt/sumo/bin/sumo -c merge.sumocfg --remote-port 10001"],
        )

    def test_resume_loads_only_successful_terminal_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            run = output / "eval3" / "seed-23"
            run.mkdir(parents=True)
            (run / "manifest.json").write_text(
                json.dumps(
                    {
                        "case": "eval3",
                        "seed": 23,
                        "exit_code": 0,
                        "source_unchanged": True,
                    }
                )
            )
            reports = QUEUE.load_completed_reports(output, "eval3")
            self.assertEqual([report["seed"] for report in reports], [23])

    def test_resume_rejects_incomplete_existing_run(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            run = output / "eval3" / "seed-23"
            run.mkdir(parents=True)
            (run / "manifest.json").write_text(
                json.dumps({"case": "eval3", "seed": 23})
            )
            with self.assertRaisesRegex(RuntimeError, "cannot be retried"):
                QUEUE.load_completed_reports(output, "eval3")


if __name__ == "__main__":
    unittest.main()

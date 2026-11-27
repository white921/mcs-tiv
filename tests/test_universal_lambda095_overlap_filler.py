import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QUEUE = load(
    "universal_lambda095_holdout_queue_for_filler_test",
    "scripts/run_universal_lambda095_holdout.py",
)
FILLER = load(
    "universal_lambda095_overlap_filler_test",
    "scripts/run_universal_lambda095_overlap_filler.py",
)


class UniversalLambda095OverlapFillerTests(unittest.TestCase):
    def test_classifies_completed_running_and_unstarted_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = QUEUE.build_ordered_tasks()
            completed_task = tasks[0]
            running_task = tasks[1]
            completed_run = FILLER.run_directory(
                root, QUEUE, completed_task, "20261127"
            )
            completed_run.mkdir(parents=True)
            (completed_run / "manifest.json").write_text(
                json.dumps(
                    {
                        "case": "eval3",
                        "seed": 23,
                        "exit_code": 0,
                        "source_unchanged": True,
                    }
                )
            )
            running_run = FILLER.run_directory(
                root, QUEUE, running_task, "20261127"
            )
            running_run.mkdir(parents=True)
            (running_run / "manifest.json").write_text(
                json.dumps(
                    {
                        "case": "eval3",
                        "seed": 24,
                        "exit_code": None,
                        "source_unchanged": None,
                    }
                )
            )
            commands = [
                "101 /opt/sumo/bin/sumo --fcd-output "
                f"{running_run.resolve()}/fcd.xml.gz"
            ]

            completed, running, queued, reports = FILLER.classify_existing_tasks(
                root, QUEUE, "20261127", commands
            )

            self.assertEqual(completed, {completed_task})
            self.assertEqual(running, {running_task})
            self.assertEqual(queued, tasks[2:])
            self.assertEqual([report["seed"] for report in reports], [23])

    def test_rejects_orphaned_run_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = QUEUE.build_ordered_tasks()[0]
            FILLER.run_directory(root, QUEUE, task, "20261127").mkdir(
                parents=True
            )
            with self.assertRaisesRegex(RuntimeError, "orphaned"):
                FILLER.classify_existing_tasks(
                    root, QUEUE, "20261127", commands=[]
                )


if __name__ == "__main__":
    unittest.main()

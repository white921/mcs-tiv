import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "accept_lock_sweep_finalizer",
    ROOT / "scripts" / "finalize_intersection_accept_lock_sweep.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def cell(speed, stop, baseline_speed=10.0):
    return {
        "mean": {"mean_speed_mps": baseline_speed},
        "delta_from_baseline": {
            "mean_speed_mps": speed,
            "stop_time_s": stop,
        },
    }


class IntersectionAcceptLockSweepFinalizerTest(unittest.TestCase):
    def test_candidate_must_improve_both_topologies(self):
        conditions = {}
        for name in ("eval3", "eval5"):
            conditions[name] = {"cells": {
                "1.0": cell(0.0, 0.0),
                "0.3": cell(0.2, -2.0),
                "0.5": cell(0.1, -1.0),
                "0.7": cell(0.05, -0.5),
            }}
        conditions["eval3"]["cells"]["0.3"] = cell(-0.1, -2.0)
        result = MODULE.choose_candidate(conditions)
        self.assertNotIn(0.3, result["eligible_candidates_s"])
        self.assertEqual(result["selected_accept_lock_s"], 0.5)

    def test_no_candidate_when_stop_time_worsens(self):
        conditions = {
            name: {"cells": {
                "1.0": cell(0.0, 0.0),
                "0.3": cell(0.2, 1.0),
                "0.5": cell(0.2, 1.0),
                "0.7": cell(0.2, 1.0),
            }} for name in ("eval3", "eval5")
        }
        result = MODULE.choose_candidate(conditions)
        self.assertEqual(result["eligible_candidates_s"], [])
        self.assertIsNone(result["selected_accept_lock_s"])


if __name__ == "__main__":
    unittest.main()

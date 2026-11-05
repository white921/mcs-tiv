import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "capture_oracle_holdout_checkpoints",
    ROOT / "scripts" / "capture_oracle_holdout_checkpoints.py")
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


class OracleHoldoutCheckpointCaptureTest(unittest.TestCase):
    def test_fixed_plan_shape_has_sixty_groups_of_sixteen(self):
        events = []
        for case in ("eval3", "eval5", "eval7"):
            for origin in ("yamashita", "proposal"):
                for seed in range(23, 33):
                    for ordinal in range(1, 17):
                        events.append({
                            "case": case, "origin_policy": origin,
                            "seed": seed, "ordinal": ordinal,
                        })
        grouped = {}
        for event in events:
            key = (event["case"], event["origin_policy"], event["seed"])
            grouped.setdefault(key, []).append(event)
        self.assertEqual(len(grouped), 60)
        self.assertTrue(all(len(group) == 16 for group in grouped.values()))


if __name__ == "__main__":
    unittest.main()

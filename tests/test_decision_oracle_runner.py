import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_decision_oracle


class DecisionOracleRunnerTests(unittest.TestCase):
    def test_branch_samples_uses_open_closed_ten_second_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "states.jsonl"
            frames = [
                {"sim_time": 27.4, "vehicles": [{
                    "vehicle_id": "1", "speed_mps": 4,
                    "allowed_speed_mps": 8, "accel_mps2": 0}]},
                {"sim_time": 27.5, "vehicles": [{
                    "vehicle_id": "1", "speed_mps": 5,
                    "allowed_speed_mps": 10, "accel_mps2": -1}]},
                {"sim_time": 37.4, "vehicles": [{
                    "vehicle_id": "1", "speed_mps": 6,
                    "allowed_speed_mps": 10, "accel_mps2": -2}]},
                {"sim_time": 37.5, "vehicles": [{
                    "vehicle_id": "1", "speed_mps": 7,
                    "allowed_speed_mps": 10, "accel_mps2": -3}]},
            ]
            path.write_text("".join(json.dumps(frame) + "\n" for frame in frames))
            samples = run_decision_oracle.branch_samples(path, 27.4, 37.4)
            self.assertEqual([sample["speed_mps"] for sample in samples["1"]],
                             [5, 6])


if __name__ == "__main__":
    unittest.main()

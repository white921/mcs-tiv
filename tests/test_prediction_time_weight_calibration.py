import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "calibrate_prediction_time_weights",
    ROOT / "scripts" / "calibrate_prediction_time_weights.py")
CALIBRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CALIBRATION)


class PredictionTimeWeightCalibrationTests(unittest.TestCase):
    def test_fit_recovers_inverse_rmse_half_life(self):
        summary = [
            {"second": second, "speed_rmse_mps": 2 ** (second / 2)}
            for second in range(11)
        ]

        self.assertAlmostEqual(CALIBRATION.fit_half_life(summary), 2.0)


if __name__ == "__main__":
    unittest.main()

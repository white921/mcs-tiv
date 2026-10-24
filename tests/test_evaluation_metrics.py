import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "func"))
import evaluation_metrics


class EvaluationMetricsTests(unittest.TestCase):
    def test_sumo_allowed_speed_is_the_shortfall_reference(self):
        bus = SimpleNamespace(type="Bus")
        self.assertEqual(evaluation_metrics._reference_speed(bus, "bus-1", {"bus-1": 11.11}), 11.11)

    def test_bus_fallback_does_not_use_car_speed(self):
        bus = SimpleNamespace(type="Bus")
        self.assertEqual(evaluation_metrics._reference_speed(bus, "bus-1", {}), 11.11)

    def test_car_fallback_is_the_configured_car_speed(self):
        car = SimpleNamespace(type="Car")
        self.assertEqual(evaluation_metrics._reference_speed(car, "car-1", {}), 13.89)


if __name__ == "__main__":
    unittest.main()

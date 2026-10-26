import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "func"))
import evaluation_metrics


class EvaluationMetricsTests(unittest.TestCase):
    def setUp(self):
        self.original_audit = evaluation_metrics.AUDIT
        evaluation_metrics.AUDIT = "enabled-for-test"
        evaluation_metrics.COUNTS.clear()
        evaluation_metrics.PHYSICAL_COLLISION_FRAMES.clear()
        evaluation_metrics.ACTIVE_PHYSICAL_COLLISIONS.clear()

    def tearDown(self):
        evaluation_metrics.AUDIT = self.original_audit
        evaluation_metrics.COUNTS.clear()
        evaluation_metrics.PHYSICAL_COLLISION_FRAMES.clear()
        evaluation_metrics.ACTIVE_PHYSICAL_COLLISIONS.clear()

    def test_sumo_allowed_speed_is_the_shortfall_reference(self):
        bus = SimpleNamespace(type="Bus")
        self.assertEqual(evaluation_metrics._reference_speed(bus, "bus-1", {"bus-1": 11.11}), 11.11)

    def test_bus_fallback_does_not_use_car_speed(self):
        bus = SimpleNamespace(type="Bus")
        self.assertEqual(evaluation_metrics._reference_speed(bus, "bus-1", {}), 11.11)

    def test_car_fallback_is_the_configured_car_speed(self):
        car = SimpleNamespace(type="Car")
        self.assertEqual(evaluation_metrics._reference_speed(car, "car-1", {}), 13.89)

    def test_sumo_physical_collision_is_counted_as_one_episode(self):
        collision = SimpleNamespace(
            collider="1", victim="2", colliderType="CAV_0",
            victimType="CAV_1", colliderSpeed=3.0, victimSpeed=0.0,
            type="collision", lane="left_0", pos=149.0)
        simulation = SimpleNamespace(
            getCollisions=lambda: (collision,),
            getCollidingVehiclesIDList=lambda: ("1", "2"))
        traci = SimpleNamespace(simulation=simulation)

        evaluation_metrics.observe_sumo_safety(traci, 10.0)
        evaluation_metrics.observe_sumo_safety(traci, 10.1)

        self.assertEqual(evaluation_metrics.COUNTS["sumo_safety_steps_observed"], 2)
        self.assertEqual(evaluation_metrics.COUNTS["sumo_collision_steps"], 2)
        self.assertEqual(evaluation_metrics.COUNTS["sumo_unique_collision_episodes"], 1)
        self.assertAlmostEqual(
            evaluation_metrics.COUNTS["sumo_collision_pair_time_s"], 0.2)
        self.assertAlmostEqual(
            evaluation_metrics.COUNTS["sumo_colliding_vehicle_time_s"], 0.4)
        self.assertEqual(len(evaluation_metrics.PHYSICAL_COLLISION_FRAMES), 2)

    def test_collision_episode_restarts_after_a_clear_step(self):
        collision = SimpleNamespace(
            collider="1", victim="2", colliderType="CAV_0",
            victimType="CAV_1", colliderSpeed=3.0, victimSpeed=0.0,
            type="collision", lane="left_0", pos=149.0)
        state = {"collisions": (collision,), "ids": ("1", "2")}
        simulation = SimpleNamespace(
            getCollisions=lambda: state["collisions"],
            getCollidingVehiclesIDList=lambda: state["ids"])
        traci = SimpleNamespace(simulation=simulation)

        evaluation_metrics.observe_sumo_safety(traci, 10.0)
        state.update(collisions=(), ids=())
        evaluation_metrics.observe_sumo_safety(traci, 10.1)
        state.update(collisions=(collision,), ids=("1", "2"))
        evaluation_metrics.observe_sumo_safety(traci, 10.2)

        self.assertEqual(evaluation_metrics.COUNTS["sumo_unique_collision_episodes"], 2)


if __name__ == "__main__":
    unittest.main()

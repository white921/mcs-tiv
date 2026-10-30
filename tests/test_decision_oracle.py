import sys
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "func"))
import decision_oracle as oracle
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import summarize_decision_oracle
import thesis_tiv


class DecisionOracleTests(unittest.TestCase):
    def test_fingerprint_detects_cursor_and_state_change(self):
        args = dict(sim_time_s=3.0, vehicle_states=[{"id": "a", "x": 1, "y": 2, "speed": 3}],
                    fixed_input_cursor={"left": 2}, random_state="rng", controller_state_hash="state")
        self.assertEqual(oracle.checkpoint_fingerprint(**args), oracle.checkpoint_fingerprint(**args))
        args["fixed_input_cursor"] = {"left": 3}
        self.assertNotEqual(oracle.checkpoint_fingerprint(**args), oracle.checkpoint_fingerprint(**{**args, "fixed_input_cursor": {"left": 2}}))

    def test_delay_integral_and_union_cohort(self):
        metrics = oracle.realised_metrics({"a": [{"speed_mps": 5, "reference_speed_mps": 10, "accel_mps2": -4}],
                                           "b": [{"speed_mps": 10, "reference_speed_mps": 10}]}, {"a", "b"})
        self.assertAlmostEqual(metrics["delay_s"], .05)
        self.assertAlmostEqual(metrics["lost_distance_m"], .5)
        self.assertAlmostEqual(metrics["distance_m"], 1.5)
        self.assertAlmostEqual(metrics["hard_brake_time_s"], .1)

    def test_safety_invalid_and_regret(self):
        accept = {"distance_m": 4.0, "safety": {"valid": True}}
        reject = {"distance_m": 2.0, "safety": {"valid": True}}
        decision = oracle.oracle_choice(accept, reject)
        self.assertEqual(decision["choice"], "accept")
        score = oracle.score_policy("reject", accept, reject, decision)
        self.assertFalse(score["correct"])
        self.assertEqual(score["regret_m"], 2.0)
        reject["safety"] = {"valid": False}
        self.assertFalse(oracle.oracle_choice(accept, reject)["valid"])

    def test_primary_cohort_is_independent_of_proposal_followers(self):
        cohort = oracle.primary_cohort_ids(
            {"actor": [], "accept-only": []},
            {"actor": [], "reject-only": []},
            {"actor"},
        )
        self.assertEqual(
            cohort, {"actor", "accept-only", "reject-only"})

    def test_one_metre_difference_is_a_tie(self):
        accept = {"distance_m": 3.0, "safety": {"valid": True}}
        reject = {"distance_m": 2.0, "safety": {"valid": True}}
        self.assertEqual(oracle.oracle_choice(accept, reject)["choice"], "tie")

    def test_summary(self):
        events = [{"oracle": {"valid": True, "choice": "accept"},
                   "policy_scores": {"proposal": {"scored": True, "correct": True, "regret_m": 0}}},
                  {"oracle": {"valid": False, "reason": "accept:safety_invalid"}}]
        total = oracle.summarize(events)
        self.assertEqual(total["events_valid"], 1)
        self.assertEqual(total["invalid_reasons"]["accept:safety_invalid"], 1)

    def test_policy_choices_reuse_one_boundary_evaluation(self):
        choices = oracle.policy_choices("reject", {
            "arrival_status": "both_reached",
            "arrival_margin_s": -0.5,
            "loss_margin_s": 1.0,
        })
        self.assertEqual(choices["yamashita"], "reject")
        self.assertEqual(choices["arrival_only"], "accept")
        self.assertEqual(choices["proposal_lambda_0.25"], "accept")
        self.assertEqual(choices["proposal_lambda_0.5"], "accept")
        self.assertEqual(choices["proposal_lambda_0.75"], "reject")
        self.assertEqual(choices["proposal_lambda_1"], "reject")

    def test_completed_event_requires_matching_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "events" / "0001"
            root.mkdir(parents=True)
            branch = {"completed": True, "restore_fingerprint_match": True,
                      "metrics": {"distance_m": 3.0, "safety": {"valid": True}}}
            event = {"schema": "decision-oracle-event-v1", "branches":
                     {"accept": branch, "reject": {**branch, "metrics": {"distance_m": 1.0, "safety": {"valid": True}}}},
                     "policy_choices": {"proposal": "accept"}}
            (root / "manifest.json").write_text(json.dumps(event))
            output = summarize_decision_oracle.read_event(root)
            self.assertEqual(output["oracle"]["choice"], "accept")

    def test_boundary_is_single_use_and_requires_matching_restore(self):
        request = oracle.DecisionRequest(1, 27.4, "15", "13", "13_23", "15_5",
                                         "accept", "reject", {"left": 4})
        boundary = oracle.BoundaryState(request, "fingerprint")
        with self.assertRaises(ValueError):
            boundary.resume("different", "accept")
        self.assertEqual(boundary.resume("fingerprint", "reject"), "reject")
        with self.assertRaises(RuntimeError):
            boundary.resume("fingerprint", "accept")
        self.assertEqual(boundary.checkpoint_payload()["pending_request"]["sender_id"], "13")

    def test_apply_decision_is_single_use(self):
        request = {"applied": False}
        self.assertEqual(thesis_tiv.apply_decision(request, "accept"), "accept")
        with self.assertRaises(RuntimeError):
            thesis_tiv.apply_decision(request, "reject")

    def test_apply_negotiation_request_rejects_without_accept_side_effects(self):
        desired = NS(pathID="13_23", vehID="13")
        vehicle = NS(
            id="15", simTime=27.4, alter_straight_path=object(),
            yetJudgedList=[], count_refuse_utility=0, count_accept_utility=0,
            pathID=5, WithAgreementPhase=True)
        request = {
            "vehicle": vehicle, "desired": desired, "collision": {},
            "received": {"value": 1}, "planned": {"value": 2},
            "prediction_method": "test", "applied": False,
        }
        with patch.object(thesis_tiv.diagnostic_trace, "record_negotiation"):
            self.assertEqual(
                thesis_tiv.apply_negotiation_request(request, "reject"),
                "rejected")
        self.assertIsNone(vehicle.alter_straight_path)
        self.assertEqual(vehicle.yetJudgedList, ["13_23"])
        self.assertEqual(vehicle.count_refuse_utility, 1)
        with self.assertRaises(RuntimeError):
            thesis_tiv.apply_negotiation_request(request, "accept")


if __name__ == "__main__":
    unittest.main()

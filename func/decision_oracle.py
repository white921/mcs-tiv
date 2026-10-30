"""Decision-level accept/reject oracle accounting.

This module intentionally contains no policy equation.  It validates that two
branches start from the same controller/SUMO checkpoint and scores their
*realised* 0.1 s motion over a common cohort.  It is kept separate from the
online TIV/proposal code so an oracle label can never accidentally contain a
policy objective.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass, asdict

DT = 0.1
HORIZON_S = 10.0
TIE_TOLERANCE_S = 1e-6


@dataclass(frozen=True)
class DecisionRequest:
    """Serializable pre-side-effect boundary for one negotiation.

    Object references remain in the controller checkpoint; this record is the
    stable identity/value witness used to rebuild and validate that request.
    """
    ordinal: int
    sim_time_s: float
    receiver_id: str
    sender_id: str
    desired_path_id: str
    alternative_path_id: str
    yamashita_choice: str
    proposal_choice: str | None
    fixed_input_cursor: object

    def manifest(self):
        return asdict(self)


class BoundaryState:
    """Single-use choice gate persisted with an MCS decision checkpoint."""
    def __init__(self, request, captured_fingerprint):
        self.request = request
        self.captured_fingerprint = captured_fingerprint
        self.applied_choice = None

    def resume(self, fingerprint, choice):
        if fingerprint != self.captured_fingerprint:
            raise ValueError("decision-boundary restore fingerprint mismatch")
        if choice not in ("accept", "reject"):
            raise ValueError("decision boundary choice must be accept or reject")
        if self.applied_choice is not None:
            raise RuntimeError("decision boundary applied more than once")
        self.applied_choice = choice
        return choice

    def checkpoint_payload(self):
        return {"pending_request": self.request.manifest(),
                "captured_fingerprint": self.captured_fingerprint,
                "applied_choice": self.applied_choice}


def canonical_hash(value):
    """Stable SHA-256 of JSON-compatible state used in restore manifests."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def checkpoint_fingerprint(*, sim_time_s, vehicle_states, fixed_input_cursor,
                           random_state, controller_state_hash):
    """Only compact, observable fields are compared between restored branches."""
    vehicles = [{"id": str(item["id"]), "x": float(item["x"]),
                 "y": float(item["y"]), "speed": float(item["speed"])}
                for item in vehicle_states]
    return canonical_hash({"time": float(sim_time_s),
                           "vehicles": sorted(vehicles, key=lambda item: item["id"]),
                           "fixed_input_cursor": fixed_input_cursor,
                           "random_state": random_state,
                           "controller_state_hash": controller_state_hash})


def realised_metrics(samples, cohort):
    """Integrate D_i=max(0,1-v/v_ref) at exactly the simulator cadence.

    ``samples`` is a mapping ``vehicle_id -> [{speed_mps, reference_speed_mps,
    accel_mps2}, ...]``.  Vehicles absent for a sample simply have no motion
    contribution; the cohort itself is supplied by the union of both branches.
    """
    result = {"delay_s": 0.0, "lost_distance_m": 0.0, "speed_sum_mps": 0.0,
              "speed_samples": 0, "stop_time_s": 0.0, "hard_brake_time_s": 0.0,
              "arrived_vehicle_ids": [], "invalid_reason": None}
    for vehicle_id in sorted(cohort):
        for sample in samples.get(str(vehicle_id), ()):
            speed, reference = float(sample["speed_mps"]), float(sample["reference_speed_mps"])
            if not (math.isfinite(speed) and math.isfinite(reference) and reference > 0):
                result["invalid_reason"] = "nonphysical_speed_or_reference"
                return result
            shortfall = max(0.0, 1.0 - speed / reference)
            result["delay_s"] += DT * shortfall
            result["lost_distance_m"] += DT * max(0.0, reference - speed)
            result["speed_sum_mps"] += speed
            result["speed_samples"] += 1
            result["stop_time_s"] += DT if speed < 0.1 else 0.0
            result["hard_brake_time_s"] += DT if float(sample.get("accel_mps2", 0.0)) <= -3.0 else 0.0
    result["mean_speed_mps"] = (result["speed_sum_mps"] / result["speed_samples"]
                                if result["speed_samples"] else None)
    return result


def oracle_choice(accept, reject, tie_tolerance_s=TIE_TOLERANCE_S):
    """Return accept/reject/tie, excluding unsafe or incomplete branches."""
    for name, branch in (("accept", accept), ("reject", reject)):
        if branch.get("invalid_reason"):
            return {"valid": False, "reason": name + ":" + branch["invalid_reason"]}
        if not branch.get("safety", {}).get("valid", False):
            return {"valid": False, "reason": name + ":safety_invalid"}
    difference = float(accept["delay_s"]) - float(reject["delay_s"])
    choice = "tie" if abs(difference) <= tie_tolerance_s else ("accept" if difference < 0 else "reject")
    return {"valid": True, "choice": choice, "difference_s": difference,
            "tie_tolerance_s": tie_tolerance_s}


def score_policy(choice, accept, reject, oracle):
    """Accuracy and regret against a valid decision oracle; ties incur no regret."""
    if not oracle.get("valid"):
        return {"scored": False, "reason": oracle.get("reason")}
    if choice not in ("accept", "reject"):
        return {"scored": False, "reason": "invalid_policy_choice"}
    selected = accept if choice == "accept" else reject
    optimum = min(float(accept["delay_s"]), float(reject["delay_s"]))
    return {"scored": True, "correct": oracle["choice"] == "tie" or choice == oracle["choice"],
            "regret_s": max(0.0, float(selected["delay_s"]) - optimum)}


def summarize(events):
    """Aggregate valid decision records without silently dropping invalid cases."""
    output = {"events_total": len(events), "events_valid": 0,
              "invalid_reasons": defaultdict(int), "policies": {}}
    for event in events:
        oracle = event.get("oracle", {})
        if not oracle.get("valid"):
            output["invalid_reasons"][oracle.get("reason", "unknown")] += 1
            continue
        output["events_valid"] += 1
        for name, score in event.get("policy_scores", {}).items():
            if not score.get("scored"):
                continue
            bucket = output["policies"].setdefault(name, {"n": 0, "correct": 0, "regrets_s": []})
            bucket["n"] += 1
            bucket["correct"] += int(bool(score["correct"]))
            bucket["regrets_s"].append(float(score["regret_s"]))
    output["invalid_reasons"] = dict(output["invalid_reasons"])
    for bucket in output["policies"].values():
        regrets = sorted(bucket.pop("regrets_s"))
        bucket["accuracy"] = bucket["correct"] / bucket["n"] if bucket["n"] else None
        bucket["mean_regret_s"] = sum(regrets) / len(regrets) if regrets else None
        bucket["median_regret_s"] = regrets[(len(regrets) - 1) // 2] if regrets else None
        bucket["p95_regret_s"] = regrets[min(len(regrets) - 1, math.ceil(.95 * len(regrets)) - 1)] if regrets else None
    return output

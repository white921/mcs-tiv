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
TIE_TOLERANCE_M = 1.0
# Backward-compatible alias for old smoke manifests.  New benchmark records
# always name the unit explicitly as metres.
TIE_TOLERANCE_S = TIE_TOLERANCE_M


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


def _path_witness(path):
    if path is None:
        return None
    samples = {}
    for name in ("t", "x", "y", "s_d", "yaw"):
        values = getattr(path, name, None)
        if values is not None:
            samples[name] = [float(value) for value in values]
    return {"path_id": str(getattr(path, "pathID", None)), "samples": samples}


def _controller_witness(vehicle):
    return {
        "id": str(vehicle.id),
        "status": getattr(vehicle, "status", None),
        "route": getattr(vehicle, "route", None),
        "road": getattr(vehicle, "road", None),
        "lane": getattr(vehicle, "lane", None),
        "path_counter": getattr(vehicle, "pathID", None),
        "is_path_valid": bool(getattr(vehicle, "isPathValid", False)),
        "is_wait_agree": bool(getattr(vehicle, "isWaitAgree", False)),
        "wait_agree_ids": list(getattr(vehicle, "waitAgreeID", []) or []),
        "receive_agree_ids": list(getattr(vehicle, "receiveAgreeID", []) or []),
        "yet_judged_ids": list(getattr(vehicle, "yetJudgedList", []) or []),
        "leader": str(getattr(vehicle, "leader", None)),
        "planned": _path_witness(getattr(vehicle, "plannedPath", None)),
        "desired": [_path_witness(path) for path in
                    (getattr(vehicle, "desiredPaths", None) or [])],
        "alternative": _path_witness(
            getattr(vehicle, "alter_straight_path", None)),
        "wait_path": _path_witness(getattr(vehicle, "waitPath", None)),
        "received": [_path_witness(path) for path in
                     (getattr(vehicle, "receivedPaths", None) or [])],
    }


def boundary_context(*, request_manifest, traci, vehicles,
                     fixed_input_schedule, python_random_state,
                     vehicle_type_random_state):
    """Build the scenario-independent decision-boundary replay witness."""
    running_ids = sorted(str(value) for value in traci.vehicle.getIDList())
    physical = []
    for vehicle_id in running_ids:
        x, y = traci.vehicle.getPosition(vehicle_id)
        physical.append({"id": vehicle_id, "x": float(x), "y": float(y),
                         "speed": float(traci.vehicle.getSpeed(vehicle_id))})
    fixed_cursor = (fixed_input_schedule.cursor()
                    if fixed_input_schedule is not None else None)
    controllers = sorted((_controller_witness(vehicle) for vehicle in vehicles),
                         key=lambda item: item["id"])
    return {
        "request": request_manifest,
        "sim_time_s": float(traci.simulation.getTime()),
        "physical_vehicles": physical,
        "fixed_input_cursor": fixed_cursor,
        "python_random_state_hash": canonical_hash(repr(python_random_state)),
        "vehicle_type_random_state_hash": canonical_hash(
            repr(vehicle_type_random_state)),
        "controller_state_hash": canonical_hash(controllers),
    }


def realised_metrics(samples, cohort):
    """Integrate realised motion at exactly the simulator cadence.

    ``samples`` is a mapping ``vehicle_id -> [{speed_mps, reference_speed_mps,
    accel_mps2}, ...]``.  Vehicles absent for a sample simply have no motion
    contribution.  ``distance_m`` is the benchmark's primary outcome; the
    normalised delay and lost-distance values are retained as diagnostics.
    """
    result = {"distance_m": 0.0, "delay_s": 0.0,
              "lost_distance_m": 0.0, "speed_sum_mps": 0.0,
              "speed_samples": 0, "stop_time_s": 0.0, "hard_brake_time_s": 0.0,
              "arrived_vehicle_ids": [], "invalid_reason": None}
    for vehicle_id in sorted(cohort):
        for sample in samples.get(str(vehicle_id), ()):
            speed, reference = float(sample["speed_mps"]), float(sample["reference_speed_mps"])
            if not (math.isfinite(speed) and math.isfinite(reference) and reference > 0):
                result["invalid_reason"] = "nonphysical_speed_or_reference"
                return result
            shortfall = max(0.0, 1.0 - speed / reference)
            result["distance_m"] += DT * speed
            result["delay_s"] += DT * shortfall
            result["lost_distance_m"] += DT * max(0.0, reference - speed)
            result["speed_sum_mps"] += speed
            result["speed_samples"] += 1
            result["stop_time_s"] += DT if speed < 0.1 else 0.0
            result["hard_brake_time_s"] += DT if float(sample.get("accel_mps2", 0.0)) <= -3.0 else 0.0
    result["mean_speed_mps"] = (result["speed_sum_mps"] / result["speed_samples"]
                                if result["speed_samples"] else None)
    return result


def primary_cohort_ids(accept_samples, reject_samples, actor_ids=()):
    """Use a policy-independent union of every vehicle observed in either branch.

    Vehicles unaffected by the forced decision contribute the same distance to
    both branches and therefore cancel.  Including them is safer than selecting
    the primary cohort from a proposal-specific predicted follower set.
    """
    return ({str(value) for value in actor_ids}
            | {str(value) for value in accept_samples}
            | {str(value) for value in reject_samples})


def oracle_choice(accept, reject, tie_tolerance_m=TIE_TOLERANCE_M):
    """Choose the branch with greater realised 10-second travel distance."""
    for name, branch in (("accept", accept), ("reject", reject)):
        if branch.get("invalid_reason"):
            return {"valid": False, "reason": name + ":" + branch["invalid_reason"]}
        if not branch.get("safety", {}).get("valid", False):
            return {"valid": False, "reason": name + ":safety_invalid"}
    difference = float(accept["distance_m"]) - float(reject["distance_m"])
    choice = ("tie" if abs(difference) <= tie_tolerance_m
              else ("accept" if difference > 0 else "reject"))
    return {"valid": True, "choice": choice,
            "accept_minus_reject_distance_m": difference,
            "tie_tolerance_m": tie_tolerance_m}


def score_policy(choice, accept, reject, oracle):
    """Accuracy and regret against a valid decision oracle; ties incur no regret."""
    if not oracle.get("valid"):
        return {"scored": False, "reason": oracle.get("reason")}
    if choice not in ("accept", "reject"):
        return {"scored": False, "reason": "invalid_policy_choice"}
    selected = accept if choice == "accept" else reject
    optimum = max(float(accept["distance_m"]), float(reject["distance_m"]))
    return {"scored": True, "correct": oracle["choice"] == "tie" or choice == oracle["choice"],
            "regret_m": max(0.0, optimum - float(selected["distance_m"]))}


def policy_choices(yamashita_choice, proposal_evaluation,
                   lambdas=(0.25, 0.5, 0.75, 1.0, 2.0)):
    """Evaluate all planned decision rules on one immutable boundary state."""
    choices = {"yamashita": yamashita_choice}
    if not proposal_evaluation:
        choices["arrival_only"] = None
        for value in lambdas:
            choices[f"proposal_lambda_{value:g}"] = None
        return choices
    arrival_status = proposal_evaluation.get("arrival_status")
    if arrival_status == "both_reached":
        arrival = float(proposal_evaluation["arrival_margin_s"])
        loss = float(proposal_evaluation["loss_margin_s"])
        effective_loss = max(loss, 0.0)
        choices["arrival_only"] = "accept" if arrival <= 0 else "reject"
        for value in lambdas:
            choices[f"proposal_lambda_{value:g}"] = (
                "accept" if arrival + float(value) * effective_loss <= 0 else "reject")
    elif arrival_status == "receiver_unreached":
        choices["arrival_only"] = "accept"
        for value in lambdas:
            choices[f"proposal_lambda_{value:g}"] = "accept"
    elif arrival_status in ("request_unreached", "both_unreached"):
        choices["arrival_only"] = "reject"
        for value in lambdas:
            choices[f"proposal_lambda_{value:g}"] = "reject"
    else:
        choices["arrival_only"] = None
        for value in lambdas:
            choices[f"proposal_lambda_{value:g}"] = None
    return choices


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
            bucket = output["policies"].setdefault(
                name, {"n": 0, "correct": 0, "regrets_m": []})
            bucket["n"] += 1
            bucket["correct"] += int(bool(score["correct"]))
            bucket["regrets_m"].append(float(score["regret_m"]))
    output["invalid_reasons"] = dict(output["invalid_reasons"])
    for bucket in output["policies"].values():
        regrets = sorted(bucket.pop("regrets_m"))
        bucket["accuracy"] = bucket["correct"] / bucket["n"] if bucket["n"] else None
        bucket["mean_regret_m"] = sum(regrets) / len(regrets) if regrets else None
        bucket["median_regret_m"] = regrets[(len(regrets) - 1) // 2] if regrets else None
        bucket["p95_regret_m"] = regrets[min(len(regrets) - 1, math.ceil(.95 * len(regrets)) - 1)] if regrets else None
    return output

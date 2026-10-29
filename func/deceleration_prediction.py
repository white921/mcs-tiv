"""Read-only counterfactual evaluator for deceleration propagation.

This module never writes a live CAV or TraCI state. It takes the MCM paths
available at one negotiation, reconstructs the CAV planner's 10-second grid,
and propagates each changed leading trajectory to vehicles following it.
``shadow`` records the result only.
"""
from __future__ import annotations

import atexit
import copy
import json
import math
import os
from collections import Counter

from deceleration_loss import SpeedProfile, time_equivalent_decision
import evaluation_metrics
from trajectory_arrival import arrival_delay

DT = 0.1
HORIZON = 10.0
REPLAN_INTERVAL = 1.0
REPLAN_STEPS = int(round(REPLAN_INTERVAL / DT))
MAX_ACCEL = 3.0
MAX_DECEL = 5.0
HEADWAY = 1.5
STANDSTILL_GAP = 5.0
LANE_TOLERANCE = 2.0
MERGE_TOLERANCE = 1.6
ALIGNMENT_COSINE = math.cos(math.radians(30.0))
SLOW_ZONE_SPEED_TOLERANCE_MPS = 0.05


def _time_half_life_from_environment():
    value = float(os.environ.get("MCS_DECELERATION_TIME_HALF_LIFE_S", "0"))
    if not math.isfinite(value) or value < 0:
        raise ValueError("MCS_DECELERATION_TIME_HALF_LIFE_S must be non-negative")
    return value or None


TIME_HALF_LIFE_S = _time_half_life_from_environment()


def _loss_lambda_from_environment():
    value = float(os.environ.get("MCS_DECELERATION_LOSS_LAMBDA", "1"))
    if not math.isfinite(value) or value < 0:
        raise ValueError("MCS_DECELERATION_LOSS_LAMBDA must be finite and non-negative")
    return value


LOSS_LAMBDA = _loss_lambda_from_environment()

COUNTS = Counter()
RECORDS = []
# A desired MCM is normally regenerated every second.  Keep an active
# proposal decision for that one planning interval so the 0.1 s SUMO loop does
# not repeatedly negotiate the very same desired path.
ACTIVE_DECISION_UNTIL = {}
MODE = os.environ.get("MCS_DECELERATION_MODE", "off")
if MODE not in ("off", "shadow", "active"):
    raise ValueError("MCS_DECELERATION_MODE must be off, shadow, or active")


def configure(mode):
    """Select off, read-only shadow, or experimental active control."""
    global MODE
    if mode not in ("off", "shadow", "active"):
        raise ValueError("MCS_DECELERATION_MODE must be off, shadow, or active")
    MODE = mode
    ACTIVE_DECISION_UNTIL.clear()


def active_decision_is_locked(receiver, desired, now):
    """Whether this receiver already decided this desired MCM this second.

    This is deliberately only an active-control guard.  Shadow measurements
    remain able to observe every incoming packet, while the live proposal
    avoids re-applying a decision until the CAV planning interval expires.
    A new desired path ID is a new negotiation and is never locked out.
    """
    if MODE != "active":
        return False
    key = (str(receiver.id), str(desired.vehID), str(desired.pathID))
    locked = now < ACTIVE_DECISION_UNTIL.get(key, float("-inf"))
    if locked:
        COUNTS["active_duplicate_decisions_suppressed"] += 1
    return locked


def _value_at(times, values, moment):
    """Linearly sample a path and retain its terminal value after its end.

    The terminal hold is the speed part of the legacy ``CAV.extendPath``
    convention. A short MCM therefore remains evaluable for the full horizon.
    """
    if len(times) != len(values) or not times:
        raise ValueError("trajectory has inconsistent samples")
    if moment < times[0] - 1e-6:
        raise ValueError("trajectory starts after prediction time")
    if moment >= times[-1]:
        return float(values[-1])
    for index in range(1, len(times)):
        if times[index] >= moment:
            before, after = times[index - 1], times[index]
            fraction = (moment - before) / (after - before)
            return float(values[index - 1]) + fraction * (float(values[index]) - float(values[index - 1]))
    return float(values[-1])


def _profile(path, vehicle_id, now):
    times = tuple(round(now + DT * index, 3) for index in range(101))
    speeds = tuple(max(0.0, _value_at(path.t, path.s_d, moment)) for moment in times)
    return SpeedProfile(str(vehicle_id), times, speeds)


def _slow_zone_path_audit(path, now):
    """Describe the fixed-zone speed wave inside this negotiation horizon.

    The planner stores the same path before the fixed restriction as an
    aligned reference.  Comparing those two profiles distinguishes an actual
    additional slowdown from a turn/follow/yield trajectory that was already
    below the road limit.
    """
    if path is None:
        return None
    context = getattr(path, "slow_zone_context", None)
    reference = getattr(path, "slow_zone_reference_s_d", None)
    times = getattr(path, "t", None)
    speeds = getattr(path, "s_d", None)
    xs = getattr(path, "x", None)
    ys = getattr(path, "y", None)
    if not isinstance(context, dict) or not context.get("enabled"):
        return None
    if not all(hasattr(values, "__len__") for values in
               (times, speeds, reference, xs, ys)):
        return {"available": False, "reason": "missing_aligned_path_arrays"}
    lengths = {len(times), len(speeds), len(reference), len(xs), len(ys)}
    if len(lengths) != 1 or not times:
        return {"available": False, "reason": "inconsistent_aligned_path_arrays"}

    end = float(now) + HORIZON
    indices = [index for index, moment in enumerate(times)
               if float(now) - 1e-6 <= moment <= end + 1e-6]
    if not indices:
        return {"available": False, "reason": "path_outside_horizon"}

    reductions = [
        (index, float(reference[index]) - float(speeds[index]))
        for index in indices
        if float(reference[index]) - float(speeds[index]) >
        SLOW_ZONE_SPEED_TOLERANCE_MPS
    ]
    start_x = float(context["start_x_m"])
    end_x = float(context["end_x_m"])
    center_y = float(context["lane_center_y_m"])
    lateral_tolerance = float(context["lateral_tolerance_m"])
    zone_indices = [
        index for index in indices
        if (start_x <= float(xs[index]) <= end_x and
            abs(float(ys[index]) - center_y) <= lateral_tolerance)
    ]
    exited_indices = [
        index for index in indices
        if (float(xs[index]) > end_x and
            abs(float(ys[index]) - center_y) <= lateral_tolerance)
    ]
    reference_at_horizon = float(_value_at(times, reference, end))
    restricted_at_horizon = float(_value_at(times, speeds, end))
    horizon_delta = float(reference_at_horizon - restricted_at_horizon)
    recovered = bool(
        abs(horizon_delta) <= SLOW_ZONE_SPEED_TOLERANCE_MPS)
    additional_deceleration = bool(reductions)
    zone_entered = bool(zone_indices)
    zone_exited = bool(exited_indices)
    intended = bool(
        additional_deceleration and zone_entered and zone_exited and recovered)
    return {
        "available": True,
        "zone_entered_within_10s": zone_entered,
        "zone_exited_within_10s": zone_exited,
        "additional_deceleration_within_10s": additional_deceleration,
        "first_additional_deceleration_s": (
            float(times[reductions[0][0]]) - float(now) if reductions else None),
        "zone_entry_s": (
            float(times[zone_indices[0]]) - float(now) if zone_indices else None),
        "zone_exit_s": (
            float(times[exited_indices[0]]) - float(now) if exited_indices else None),
        "maximum_speed_reduction_mps": (
            max(delta for _, delta in reductions) if reductions else 0.0),
        "normal_speed_at_10s_mps": reference_at_horizon,
        "restricted_speed_at_10s_mps": restricted_at_horizon,
        "speed_difference_at_10s_mps": horizon_delta,
        "recovered_to_normal_speed_at_10s": recovered,
        "intended_temporary_slowdown": intended,
    }


def slow_zone_negotiation_audit(receiver, desired, alternative, now):
    """Return a compact, method-independent fixed-zone audit for one event."""
    candidates = _latest_planned(receiver)
    sender_id = str(getattr(desired, "vehID", "unknown"))
    receiver_id = str(receiver.id)
    role_paths = [
        ("sender_desired", desired),
        ("sender_planned", candidates.get(sender_id)),
        ("receiver_planned", getattr(receiver, "plannedPath", None)),
        ("receiver_alternative", alternative),
    ]
    actor_object_ids = {id(path) for _, path in role_paths if path is not None}
    for vehicle_id, path in sorted(candidates.items()):
        if id(path) in actor_object_ids or vehicle_id in (sender_id, receiver_id):
            continue
        role_paths.append(("received_planned", path))

    paths = []
    evaluated = []
    for role, path in role_paths:
        audit = _slow_zone_path_audit(path, now)
        if audit is None:
            continue
        item = {
            "role": role,
            "vehicle_id": str(getattr(path, "vehID", "unknown")),
            "path_id": getattr(path, "pathID", None),
            **audit,
        }
        evaluated.append(item)
        # Keep every actor path.  For ambient planned paths, retain only the
        # ones that actually reach the section or experience its speed cap.
        if (role != "received_planned" or
                audit.get("zone_entered_within_10s") or
                audit.get("additional_deceleration_within_10s")):
            paths.append(item)

    if not evaluated:
        return {
            "scenario_enabled": False,
            "evaluated_path_count": 0,
            "intended_profile_path_count": 0,
            "intended_profile_observed": False,
            "paths": [],
        }
    intended_count = sum(
        bool(item.get("intended_temporary_slowdown")) for item in evaluated)
    return {
        "scenario_enabled": True,
        "horizon_s": HORIZON,
        "speed_recovery_tolerance_mps": SLOW_ZONE_SPEED_TOLERANCE_MPS,
        "evaluated_path_count": len(evaluated),
        "zone_entered_path_count": sum(
            bool(item.get("zone_entered_within_10s")) for item in evaluated),
        "additional_deceleration_path_count": sum(
            bool(item.get("additional_deceleration_within_10s"))
            for item in evaluated),
        "intended_profile_path_count": intended_count,
        "intended_profile_observed": intended_count > 0,
        "paths": paths,
    }


def _position(path, now):
    return (_value_at(path.t, path.x, now), _value_at(path.t, path.y, now))


def _heading(path, now):
    x0, y0 = _position(path, now)
    yaw = getattr(path, "yaw", None)
    if yaw and len(yaw) == len(path.t):
        angle = _value_at(path.t, yaw, now)
        if math.isfinite(angle):
            return (x0, y0, math.cos(angle), math.sin(angle))

    # Backward compatibility for older MCM logs without yaw.  Search the
    # trajectory rather than relying on the next 0.1 s sample, because a valid
    # path may begin with a stationary interval.
    indices = sorted(range(len(path.t)), key=lambda index: abs(path.t[index] - now))
    origin = indices[0]
    for index in range(origin + 1, len(path.t)):
        dx, dy = path.x[index] - x0, path.y[index] - y0
        length = math.hypot(dx, dy)
        if length >= 1e-6:
            return (x0, y0, dx / length, dy / length)
    for index in range(origin - 1, -1, -1):
        dx, dy = x0 - path.x[index], y0 - path.y[index]
        length = math.hypot(dx, dy)
        if length >= 1e-6:
            return (x0, y0, dx / length, dy / length)
    raise ValueError("trajectory has no usable heading or yaw")


def _lane_id(path):
    value = getattr(path, "lane_id", None)
    return str(value) if value not in (None, "") else None


def _lane_position(path):
    value = getattr(path, "lane_position", None)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _sample_indices(path, now, step=5):
    indices = [index for index, moment in enumerate(path.t)
               if moment >= now - 1e-6]
    sampled = indices[::step]
    if indices and indices[-1] not in sampled:
        sampled.append(indices[-1])
    return sampled


def _future_lane_convergence(leader, candidate, now):
    """Return arrival times where different current lanes share a corridor.

    Lane IDs establish current-lane following.  For merges and turns from
    different lanes, the already-transmitted future trajectories establish a
    shared downstream corridor.  Perpendicular conflict crossings are rejected
    by the heading-alignment test.
    """
    best = None
    for leader_index in _sample_indices(leader, now):
        leader_yaw = (leader.yaw[leader_index]
                      if getattr(leader, "yaw", None) and
                      len(leader.yaw) == len(leader.t) else None)
        for candidate_index in _sample_indices(candidate, now):
            distance = math.hypot(
                leader.x[leader_index] - candidate.x[candidate_index],
                leader.y[leader_index] - candidate.y[candidate_index])
            if distance > MERGE_TOLERANCE:
                continue
            candidate_yaw = (candidate.yaw[candidate_index]
                             if getattr(candidate, "yaw", None) and
                             len(candidate.yaw) == len(candidate.t) else None)
            if leader_yaw is None or candidate_yaw is None:
                continue
            if math.cos(leader_yaw - candidate_yaw) < ALIGNMENT_COSINE:
                continue
            leader_time = float(leader.t[leader_index])
            candidate_time = float(candidate.t[candidate_index])
            if candidate_time + DT < leader_time:
                continue
            key = (max(leader_time, candidate_time), candidate_time - leader_time)
            if best is None or key < best[0]:
                best = (key, leader_time, candidate_time)
    return None if best is None else best[1:]


def _latest_planned(receiver):
    latest = {}
    for path in receiver.receivedPaths:
        if getattr(path, "type", None) != "planned" or not getattr(path, "t", None):
            continue
        previous = latest.get(str(path.vehID))
        if previous is None or path.t[0] > previous.t[0]:
            latest[str(path.vehID)] = path
    return latest


def _followers(leader_id, leader_path, candidates, now, excluded):
    """Return current-lane and future-merge followers, nearest first."""
    x, y, hx, hy = _heading(leader_path, now)
    leader_lane = _lane_id(leader_path)
    leader_lane_position = _lane_position(leader_path)
    queue = []
    for vehicle_id, path in candidates.items():
        if vehicle_id in excluded or vehicle_id == leader_id:
            continue
        px, py = _position(path, now)
        dx, dy = px - x, py - y
        longitudinal = dx * hx + dy * hy
        lateral = abs(dx * hy - dy * hx)
        candidate_lane = _lane_id(path)
        if leader_lane is not None and candidate_lane is not None:
            if leader_lane == candidate_lane:
                candidate_lane_position = _lane_position(path)
                if (leader_lane_position is not None and
                        candidate_lane_position is not None):
                    lane_separation = leader_lane_position - candidate_lane_position
                    if lane_separation > 0.1:
                        gap = max(0.0, lane_separation - 5.0)
                        queue.append((0, lane_separation, vehicle_id, path, gap))
                elif longitudinal < -0.1:
                    # Compatibility with packets produced before lane position
                    # became part of the MCM context.
                    gap = max(0.0, math.hypot(dx, dy) - 5.0)
                    queue.append((0, abs(longitudinal), vehicle_id, path, gap))
                continue
            convergence = _future_lane_convergence(leader_path, path, now)
            if convergence is not None:
                leader_time, candidate_time = convergence
                candidate_speed = max(0.0, _value_at(path.t, path.s_d, now))
                gap = max(0.0, candidate_speed * (candidate_time - leader_time) - 5.0)
                queue.append((1, candidate_time - now, vehicle_id, path, gap))
            continue

        # Old logs have no lane metadata. Preserve their geometric fallback,
        # but new simulations always use the explicit lane identity above.
        if longitudinal < -0.1 and lateral <= LANE_TOLERANCE:
            gap = max(0.0, math.hypot(dx, dy) - 5.0)
            queue.append((0, abs(longitudinal), vehicle_id, path, gap))
    return [(vehicle_id, path, gap)
            for _, _, vehicle_id, path, gap in sorted(queue)]


def _propagate_follower(vehicle_id, base, leader, gap):
    """Predict a follower with 1 s replans and 0.1 s state integration.

    At each one-second boundary a target speed is taken from the vehicle's
    baseline CAV trajectory and a fresh bounded-acceleration segment is made.
    Between boundaries the segment is executed at SUMO's 0.1 s cadence.  A
    short-gap brake overrides that segment immediately, just as safety must
    override a stale candidate path in the live controller.
    """
    speeds = [base.speeds[0]]
    current_gap = max(0.0, gap)
    for start in range(0, 100, REPLAN_STEPS):
        end = min(start + REPLAN_STEPS, 100)
        duration = (end - start) * DT
        current = speeds[-1]
        target = base.speeds[end]
        planned_accel = max(-MAX_DECEL, min(MAX_ACCEL, (target - current) / duration))
        for index in range(start, end):
            current = speeds[-1]
            leader_speed = leader.speeds[index]
            desired_gap = STANDSTILL_GAP + HEADWAY * current
            if current_gap < desired_gap:
                next_speed = max(0.0, current - MAX_DECEL * DT)
            else:
                next_speed = max(0.0, current + planned_accel * DT)
            current_gap = max(0.0, current_gap + (leader_speed - next_speed) * DT)
            speeds.append(next_speed)
    return SpeedProfile(vehicle_id, base.times, tuple(speeds))


def _case_profiles(roots, candidates, now):
    """Build roots and their follower queues for one counterfactual case."""
    profiles = {vehicle_id: _profile(path, vehicle_id, now)
                for vehicle_id, path in roots.items()}
    assigned = set(roots)
    for root_id, root_path in roots.items():
        leader = profiles[root_id]
        leader_path = root_path
        leader_x, leader_y = _position(leader_path, now)
        for follower_id, follower_path, gap in _followers(
                root_id, leader_path, candidates, now, assigned):
            fx, fy = _position(follower_path, now)
            base = _profile(follower_path, follower_id, now)
            leader = _propagate_follower(follower_id, base, leader, gap)
            profiles[follower_id] = leader
            assigned.add(follower_id)
            leader_path = follower_path
            leader_x, leader_y = fx, fy
    return profiles


def _evaluate_detail(receiver, desired, alternative, now, conflict_point):
    """Return the comparison and both case profiles for instrumentation."""
    sender_id, receiver_id = str(desired.vehID), str(receiver.id)
    candidates = _latest_planned(receiver)
    sender_planned = candidates.get(sender_id)
    if sender_planned is None:
        raise ValueError("sender planned trajectory is unavailable")
    receiver_planned = copy.deepcopy(receiver.plannedPath)
    receiver_alternative = copy.deepcopy(alternative)
    for path in (receiver_planned, receiver_alternative):
        for name, value in (
            ("lane_id", getattr(receiver, "lane_id", None)),
            ("lane_index", getattr(receiver, "lane", None)),
            ("lane_position", getattr(receiver, "lane_position", None)),
            ("road_id", getattr(receiver, "road", None)),
            ("allowed_speed_mps", getattr(receiver, "allowed_speed_mps", None)),
        ):
            if getattr(path, name, None) in (None, ""):
                setattr(path, name, value)
    candidates[receiver_id] = receiver_planned
    reject_roots = {sender_id: sender_planned, receiver_id: receiver_planned}
    accept_roots = {sender_id: desired, receiver_id: receiver_alternative}
    reject = _case_profiles(reject_roots, candidates, now)
    accept = _case_profiles(accept_roots, candidates, now)

    # Accepting and rejecting can legitimately affect different following
    # queues.  Compare both cases over their union instead of dropping the
    # proposal evaluation.  A vehicle that is affected in only one case keeps
    # its transmitted planned profile in the other case.  This is the sparse
    # equivalent of comparing every vehicle: vehicles outside the union are
    # identical in both cases and therefore cancel from the decision margin.
    actor_ids = {sender_id, receiver_id}
    accept_follower_ids = set(accept) - actor_ids
    reject_follower_ids = set(reject) - actor_ids
    union_ids = set(accept) | set(reject)
    reference = {}
    for vehicle_id in union_ids:
        planned = candidates.get(vehicle_id)
        if planned is None:
            raise ValueError(
                "planned trajectory is unavailable for union vehicle " +
                vehicle_id)
        baseline = _profile(planned, vehicle_id, now)
        reference[vehicle_id] = baseline
        accept.setdefault(vehicle_id, baseline)
        reject.setdefault(vehicle_id, baseline)

    if conflict_point is None or len(conflict_point) != 2:
        raise ValueError("conflict point is unavailable")
    # Arrival time already evaluates the two negotiating actors directly.
    # The loss term is therefore restricted to other vehicles whose following
    # motion changes under Accept or Reject.  This avoids counting the sender
    # and receiver once in arrival priority and again in aggregate delay.
    loss_vehicle_ids = union_ids - actor_ids
    allowed_speeds = {}
    for vehicle_id in loss_vehicle_ids:
        value = getattr(candidates[vehicle_id], "allowed_speed_mps", None)
        if value is None:
            raise ValueError(
                "allowed speed is unavailable for vehicle " + vehicle_id)
        allowed_speeds[vehicle_id] = value
    result = time_equivalent_decision(
        {vehicle_id: reference[vehicle_id] for vehicle_id in loss_vehicle_ids},
        {vehicle_id: accept[vehicle_id] for vehicle_id in loss_vehicle_ids},
        {vehicle_id: reject[vehicle_id] for vehicle_id in loss_vehicle_ids},
        allowed_speeds,
        request_arrival_s=arrival_delay(desired, conflict_point, now),
        receiver_arrival_s=arrival_delay(
            receiver_planned, conflict_point, now),
        loss_lambda=LOSS_LAMBDA,
        time_half_life_s=TIME_HALF_LIFE_S)
    union_follower_ids = accept_follower_ids | reject_follower_ids
    result = {**result, "vehicle_ids": sorted(union_ids),
              "loss_vehicle_ids": sorted(loss_vehicle_ids),
              "excluded_loss_vehicle_ids": sorted(actor_ids),
              "accept_follower_ids": sorted(accept_follower_ids),
              "reject_follower_ids": sorted(reject_follower_ids),
              "union_follower_ids": sorted(union_follower_ids),
              "follower_count": len(union_follower_ids),
              "replan_interval_s": REPLAN_INTERVAL,
              "time_weighting": ("uniform" if TIME_HALF_LIFE_S is None
                                 else "exponential-half-life"),
              "time_half_life_s": TIME_HALF_LIFE_S,
              "follower_replans": len(union_follower_ids) * int(HORIZON / REPLAN_INTERVAL),
              "slow_zone_audit": slow_zone_negotiation_audit(
                  receiver, desired, alternative, now)}
    return result, accept, reject


def evaluate(receiver, desired, alternative, now, conflict_point):
    """Evaluate accept/reject with every detectable following queue."""
    return _evaluate_detail(receiver, desired, alternative, now, conflict_point)[0]


def direct_tiv_profiles(receiver, desired, alternative, now, decision):
    """Return the two trajectories TIVtep actually has when it decides.

    TIVtep does not forecast a following queue.  Its prediction-accuracy log
    must therefore be labelled as the direct sender/receiver scope rather
    than pretending that absent follower forecasts are accurate.
    """
    sender_id, receiver_id = str(desired.vehID), str(receiver.id)
    candidates = _latest_planned(receiver)
    sender_planned = candidates.get(sender_id)
    if sender_planned is None:
        raise ValueError("sender planned trajectory is unavailable")
    if decision == "accept":
        roots = {sender_id: desired, receiver_id: alternative}
    elif decision == "reject":
        roots = {sender_id: sender_planned, receiver_id: receiver.plannedPath}
    else:
        raise ValueError("decision must be accept or reject")
    return {vehicle_id: _profile(path, vehicle_id, now)
            for vehicle_id, path in roots.items()}


def _record_evaluation(receiver, desired, alternative, now, conflict_point, mode):
    """Evaluate and audit a proposal decision without mutating vehicle state."""
    if MODE != mode:
        return None
    COUNTS[mode + "_attempts"] += 1
    try:
        result, accept_profiles, reject_profiles = _evaluate_detail(
            receiver, desired, alternative, now, conflict_point)
    except (AttributeError, IndexError, TypeError, ValueError, ZeroDivisionError) as error:
        COUNTS[mode + "_unsupported"] += 1
        record = {"time": now, "receiver": str(receiver.id),
                  "sender": str(getattr(desired, "vehID", "unknown")),
                  "status": "unsupported", "reason": str(error)}
    else:
        COUNTS[mode + "_evaluations"] += 1
        COUNTS["follower_profiles"] += result["follower_count"]
        if mode == "active":
            chosen_profiles = accept_profiles if result["decision"] == "accept" else reject_profiles
            actor_ids = [str(desired.vehID), str(receiver.id)]
            evaluation_metrics.register_prediction(
                now, result["decision"], result["follower_count"], chosen_profiles,
                metadata={
                    "method": "deceleration-propagation",
                    "predictor": "10s-kinematic-following",
                    "receiver_id": str(receiver.id), "sender_id": str(desired.vehID),
                    "desired_path_id": str(desired.pathID),
                    "alternative_path_id": str(alternative.pathID),
                    "actor_vehicle_ids": actor_ids,
                    "loss_vehicle_ids": result["loss_vehicle_ids"],
                    "excluded_loss_vehicle_ids": result["excluded_loss_vehicle_ids"],
                    "follower_vehicle_ids": sorted(set(chosen_profiles) - set(actor_ids)),
                    "accept_follower_ids": result["accept_follower_ids"],
                    "reject_follower_ids": result["reject_follower_ids"],
                    "union_follower_ids": result["union_follower_ids"],
                    "prediction_scope": "sender_receiver_and_detected_followers",
                    "time_weighting": result["time_weighting"],
                    "time_half_life_s": result["time_half_life_s"],
                    "accept_loss_m": result["accept_loss_m"],
                    "reject_loss_m": result["reject_loss_m"],
                    "decision_margin_m": result["reject_minus_accept_m"],
                    "request_arrival_s": result["request_arrival_s"],
                    "receiver_arrival_s": result["receiver_arrival_s"],
                    "request_arrival_reached": result["request_arrival_reached"],
                    "receiver_arrival_reached": result["receiver_arrival_reached"],
                    "arrival_status": result["arrival_status"],
                    "decision_basis": result["decision_basis"],
                    "arrival_margin_s": result["arrival_margin_s"],
                    "accept_time_equivalent_loss_s": result["accept_time_equivalent_loss_s"],
                    "reject_time_equivalent_loss_s": result["reject_time_equivalent_loss_s"],
                    "weighted_loss_margin_s": result["weighted_loss_margin_s"],
                    "final_margin_s": result["final_margin_s"],
                    "loss_lambda": result["loss_lambda"],
                })
        record = {"time": now, "receiver": str(receiver.id), "sender": str(desired.vehID),
                  "desired_path_id": desired.pathID, "alternative_path_id": alternative.pathID,
                  "status": "evaluated", "predictor": "10s-kinematic-following",
                  **result}
    if len(RECORDS) < 500:
        RECORDS.append(record)
    return record


def record_shadow(receiver, desired, alternative, now, conflict_point):
    """Record a full 10-second comparison and leave the TIV decision intact."""
    return _record_evaluation(
        receiver, desired, alternative, now, conflict_point, "shadow")


def active_decision(receiver, desired, alternative, now, conflict_point):
    """Return the proposed decision, or ``None`` if prediction is unavailable.

    Keeping the unavailable case as ``None`` lets the caller retain the
    baseline TIV rule rather than creating an unsafe synthetic decision.
    """
    record = _record_evaluation(
        receiver, desired, alternative, now, conflict_point, "active")
    if record is None or record["status"] != "evaluated":
        return None
    key = (str(receiver.id), str(desired.vehID), str(desired.pathID))
    ACTIVE_DECISION_UNTIL[key] = now + REPLAN_INTERVAL
    return record["decision"] == "accept"


def record_tiv_comparison(proposal_accept, tiv_accept):
    """Count whether the active proposal would differ from TIV at this event."""
    if MODE != "active":
        return
    COUNTS["proposal_accept" if proposal_accept else "proposal_reject"] += 1
    COUNTS["tiv_would_accept" if tiv_accept else "tiv_would_reject"] += 1
    COUNTS["decision_agreement" if proposal_accept == tiv_accept else "decision_disagreement"] += 1


def _write_audit():
    destination = os.environ.get("MCS_DECELERATION_AUDIT")
    if destination:
        with open(destination, "w") as stream:
            json.dump(evaluation_metrics.json_safe({
                "mode": MODE, "counts": dict(COUNTS), "records": RECORDS,
            }), stream, indent=2,
                      allow_nan=False)


atexit.register(_write_audit)

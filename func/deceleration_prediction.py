"""Read-only counterfactual evaluator for deceleration propagation.

This module never writes a live CAV or TraCI state. It takes the MCM paths
available at one negotiation, reconstructs the CAV planner's 10-second grid,
and propagates each changed leading trajectory to vehicles following it.
``shadow`` records the result only.
"""
from __future__ import annotations

import atexit
import json
import math
import os
from collections import Counter

from deceleration_loss import SpeedProfile, decision_margin

DT = 0.1
HORIZON = 10.0
MAX_ACCEL = 3.0
MAX_DECEL = 5.0
HEADWAY = 1.5
STANDSTILL_GAP = 5.0
LANE_TOLERANCE = 2.0

COUNTS = Counter()
RECORDS = []
MODE = os.environ.get("MCS_DECELERATION_MODE", "off")
if MODE not in ("off", "shadow", "active"):
    raise ValueError("MCS_DECELERATION_MODE must be off, shadow, or active")


def configure(mode):
    """Select off, read-only shadow, or experimental active control."""
    global MODE
    if mode not in ("off", "shadow", "active"):
        raise ValueError("MCS_DECELERATION_MODE must be off, shadow, or active")
    MODE = mode


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


def _position(path, now):
    return (_value_at(path.t, path.x, now), _value_at(path.t, path.y, now))


def _heading(path, now):
    x0, y0 = _position(path, now)
    x1, y1 = _position(path, now + DT)
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1e-6:
        raise ValueError("trajectory has no usable heading")
    return (x0, y0, (x1 - x0) / length, (y1 - y0) / length)


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
    """Return the same-lane queue behind a leader, nearest first."""
    x, y, hx, hy = _heading(leader_path, now)
    queue = []
    for vehicle_id, path in candidates.items():
        if vehicle_id in excluded or vehicle_id == leader_id:
            continue
        px, py = _position(path, now)
        dx, dy = px - x, py - y
        longitudinal = dx * hx + dy * hy
        lateral = abs(dx * hy - dy * hx)
        if longitudinal < -0.1 and lateral <= LANE_TOLERANCE:
            queue.append((abs(longitudinal), vehicle_id, path))
    return [(vehicle_id, path) for _, vehicle_id, path in sorted(queue)]


def _propagate_follower(vehicle_id, base, leader, gap):
    """Predict a follower on the CAV's 0.1 s grid with its accel/decel caps."""
    speeds = [base.speeds[0]]
    current_gap = max(0.0, gap)
    for index in range(100):
        current = speeds[-1]
        leader_speed = leader.speeds[index]
        desired_gap = STANDSTILL_GAP + HEADWAY * current
        if current_gap < desired_gap:
            next_speed = max(0.0, current - MAX_DECEL * DT)
        else:
            next_speed = min(base.speeds[index + 1], current + MAX_ACCEL * DT)
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
        for follower_id, follower_path in _followers(root_id, leader_path, candidates, now, assigned):
            fx, fy = _position(follower_path, now)
            gap = math.hypot(leader_x - fx, leader_y - fy) - 5.0
            base = _profile(follower_path, follower_id, now)
            leader = _propagate_follower(follower_id, base, leader, gap)
            profiles[follower_id] = leader
            assigned.add(follower_id)
            leader_path = follower_path
            leader_x, leader_y = fx, fy
    return profiles


def evaluate(receiver, desired, alternative, now):
    """Evaluate accept/reject with every detectable following queue."""
    sender_id, receiver_id = str(desired.vehID), str(receiver.id)
    candidates = _latest_planned(receiver)
    sender_planned = candidates.get(sender_id)
    if sender_planned is None:
        raise ValueError("sender planned trajectory is unavailable")
    candidates[receiver_id] = receiver.plannedPath
    reject_roots = {sender_id: sender_planned, receiver_id: receiver.plannedPath}
    accept_roots = {sender_id: desired, receiver_id: alternative}
    reject = _case_profiles(reject_roots, candidates, now)
    accept = _case_profiles(accept_roots, candidates, now)
    if set(reject) != set(accept):
        raise ValueError("counterfactual cases select different follower sets")
    result = decision_margin(reject, accept, reject)
    return {**result, "vehicle_ids": sorted(reject),
            "follower_count": max(0, len(reject) - 2),
            "decision": "accept" if result["reject_minus_accept_m"] >= 0 else "reject"}


def _record_evaluation(receiver, desired, alternative, now, mode):
    """Evaluate and audit a proposal decision without mutating vehicle state."""
    if MODE != mode:
        return None
    COUNTS[mode + "_attempts"] += 1
    try:
        result = evaluate(receiver, desired, alternative, now)
    except (AttributeError, IndexError, TypeError, ValueError, ZeroDivisionError) as error:
        COUNTS[mode + "_unsupported"] += 1
        record = {"time": now, "receiver": str(receiver.id),
                  "sender": str(getattr(desired, "vehID", "unknown")),
                  "status": "unsupported", "reason": str(error)}
    else:
        COUNTS[mode + "_evaluations"] += 1
        COUNTS["follower_profiles"] += result["follower_count"]
        record = {"time": now, "receiver": str(receiver.id), "sender": str(desired.vehID),
                  "desired_path_id": desired.pathID, "alternative_path_id": alternative.pathID,
                  "status": "evaluated", "predictor": "10s-kinematic-following",
                  **result}
    if len(RECORDS) < 500:
        RECORDS.append(record)
    return record


def record_shadow(receiver, desired, alternative, now):
    """Record a full 10-second comparison and leave the TIV decision intact."""
    return _record_evaluation(receiver, desired, alternative, now, "shadow")


def active_decision(receiver, desired, alternative, now):
    """Return the proposed decision, or ``None`` if prediction is unavailable.

    Keeping the unavailable case as ``None`` lets the caller retain the
    baseline TIV rule rather than creating an unsafe synthetic decision.
    """
    record = _record_evaluation(receiver, desired, alternative, now, "active")
    if record is None or record["status"] != "evaluated":
        return None
    return record["decision"] == "accept"


def _write_audit():
    destination = os.environ.get("MCS_DECELERATION_AUDIT")
    if destination:
        with open(destination, "w") as stream:
            json.dump({"mode": MODE, "counts": dict(COUNTS), "records": RECORDS}, stream, indent=2)


atexit.register(_write_audit)

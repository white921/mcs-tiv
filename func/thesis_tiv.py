"""Thesis chapter 4. See docs/thesis-audit.md for numerical assumptions."""
import atexit
import copy
import json
import math
import os
from collections import Counter
import deceleration_prediction
import diagnostic_trace
import evaluation_metrics

COUNTS = Counter()
EXAMPLES = []
IMPLEMENTATION = os.environ.get("MCS_TIV_IMPLEMENTATION", "thesis")
if IMPLEMENTATION not in ("thesis", "legacy-local"):
    raise ValueError("invalid MCS_TIV_IMPLEMENTATION")


def conditional_priority_hold_enabled():
    """Return whether the opt-in two-stage agreement policy is active."""
    return os.environ.get("MCS_PRIORITY_HOLD_MODE", "off") == "conditional"


def _hold_float(name, default):
    value = float(os.environ.get(name, default))
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _hold_int(name, default):
    value = int(os.environ.get(name, default))
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _collision_point(collision):
    point = (collision.get("collide_x"), collision.get("collide_y"))
    return point if all(value is not None for value in point) else None


def _conflict_region(point):
    """Stable 2 m conflict-cell identifier, independent of trajectory IDs."""
    return tuple(int(math.floor(value / 2.0 + 0.5)) for value in point)


def _agreement_participants(path):
    return frozenset(str(value) for value in getattr(path, "negotiationID", []))


def _same_priority_relation(vehicle, collision):
    """Match by vehicle pair and physical conflict region, never by path ID."""
    hold = getattr(vehicle, "_mcs_priority_hold", None)
    point = _collision_point(collision)
    desired = collision["path"]
    if not hold or point is None:
        return False
    return (
        str(desired.vehID) == hold["priority_vehicle"]
        and str(vehicle.id) == hold["yielding_vehicle"]
        and (_conflict_region(point) == tuple(hold["conflict_region"])
             or math.hypot(point[0] - hold["point"][0],
                           point[1] - hold["point"][1]) <= 2.0)
    )


def _following_queue_size(traci, vehicle_id):
    """Best-effort same-lane queue length from SUMO's follower chain."""
    getter = getattr(traci.vehicle, "getFollower", None)
    if getter is None:
        return None
    count = 0
    current = str(vehicle_id)
    seen = {current}
    try:
        while count < 20:
            follower = getter(current)
            if not follower or not follower[0]:
                break
            current = str(follower[0])
            if current in seen:
                break
            seen.add(current)
            count += 1
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return count


def _priority_motion(vehicle, desired, point, traci, hold):
    """Return whether the priority vehicle can physically advance now."""
    priority_id = str(desired.vehID)
    speed = float(traci.vehicle.getSpeed(priority_id))
    position = traci.vehicle.getPosition(priority_id)
    distance = math.hypot(position[0] - point[0], position[1] - point[1])
    previous_distance = hold.get("last_distance")
    actual_progress = (previous_distance is not None
                       and previous_distance - distance >= 0.1)
    hold["last_distance"] = distance
    if actual_progress or speed >= _hold_float("MCS_PRIORITY_HOLD_ACTIVATION_SPEED", "0.5"):
        hold["last_progress_time"] = vehicle.simTime

    planned_progress = False
    try:
        indices = [i for i, timestamp in enumerate(desired.t)
                   if timestamp >= vehicle.simTime - 1e-6]
        if indices:
            now_index = indices[0]
            future_index = min(indices[-1], now_index + 10)
            distance_now = math.hypot(desired.x[now_index] - point[0],
                                      desired.y[now_index] - point[1])
            distance_future = math.hypot(desired.x[future_index] - point[0],
                                         desired.y[future_index] - point[1])
            planned_progress = distance_now - distance_future >= 0.2
    except (AttributeError, IndexError, TypeError, ValueError):
        planned_progress = False

    blocked = False
    get_leader = getattr(traci.vehicle, "getLeader", None)
    if get_leader is not None:
        try:
            leader = get_leader(priority_id, 50.0)
            blocked = bool(leader and leader[0]
                           and float(leader[1]) <= max(5.0, speed * 1.5 + 2.0))
        except (AttributeError, KeyError, TypeError, ValueError):
            blocked = False
    return (not blocked and planned_progress
            and (speed >= _hold_float("MCS_PRIORITY_HOLD_ACTIVATION_SPEED", "0.5")
                 or actual_progress)), {
        "priority_speed_mps": speed,
        "priority_distance_m": distance,
        "planned_progress": planned_progress,
        "actual_progress": actual_progress,
        "blocked_by_leader": blocked,
    }


def _clear_agreement_state(vehicle):
    vehicle.alter_straight_path = None
    if hasattr(vehicle, "alter_change_path"):
        vehicle.alter_change_path = None
    vehicle.isWaitAgree = False
    vehicle.waitAgreeID = []
    vehicle.receiveAgreeID = []
    vehicle.waitPath = None


def _release_priority_hold(vehicle, reason, collision=None, details=None):
    hold = getattr(vehicle, "_mcs_priority_hold", None)
    if hold is None:
        return
    path = (collision or {}).get("path") or getattr(vehicle, "waitPath", None)
    if path is not None:
        diagnostic_trace.record_negotiation(
            vehicle, path, "priority_hold_released", reason=reason,
            collision=collision, details={
                "hold_key": hold["key"], "hold_phase": hold["phase"],
                **(details or {}),
            })
    COUNTS["conditional_hold_released"] += 1
    COUNTS["conditional_hold_released_" + reason] += 1
    if hold.get("phase") == "awaiting_agreement":
        _clear_agreement_state(vehicle)
    if hold.get("phase") == "active" and vehicle.leader == hold["priority_vehicle"]:
        vehicle.leader = None
        vehicle.leadPath = None
        if vehicle.status == "yield":
            vehicle.status = "free"
            vehicle.isPathValid = False
    vehicle._mcs_priority_hold = None


def _new_priority_hold(vehicle, desired, collision, traci):
    point = _collision_point(collision)
    if point is None:
        return None
    participants = _agreement_participants(desired)
    hold = {
        "key": [str(desired.vehID), str(vehicle.id), list(_conflict_region(point))],
        "priority_vehicle": str(desired.vehID),
        "yielding_vehicle": str(vehicle.id),
        "conflict_region": list(_conflict_region(point)),
        "point": point,
        "participants": participants,
        "phase": "awaiting_agreement",
        "created_at": vehicle.simTime,
        "last_progress_time": vehicle.simTime,
        "last_distance": None,
        "baseline_queue": _following_queue_size(traci, vehicle.id),
        "last_pending_log": None,
    }
    vehicle._mcs_priority_hold = hold
    COUNTS["conditional_hold_remembered"] += 1
    diagnostic_trace.record_negotiation(
        vehicle, desired, "priority_hold_remembered", accept=True,
        reason="accepted_pair_and_conflict_region", collision=collision,
        details={"hold_key": hold["key"],
                 "participants": sorted(participants),
                 "phase": hold["phase"]})
    return hold


def _release_reason(vehicle, collision, traci, collisions=None):
    hold = vehicle._mcs_priority_hold
    now = vehicle.simTime
    if now - hold["created_at"] >= _hold_float("MCS_PRIORITY_HOLD_MAX_DURATION", "10"):
        return "max_duration"
    participants = _agreement_participants(collision["path"])
    if participants != hold["participants"]:
        return "conflict_participants_changed"
    if collisions is not None and any(
            not _same_priority_relation(vehicle, entry) for entry in collisions):
        return "additional_conflict"
    queue = _following_queue_size(traci, vehicle.id)
    baseline = hold.get("baseline_queue")
    if (queue is not None and baseline is not None
            and queue - baseline > _hold_int("MCS_PRIORITY_HOLD_QUEUE_GROWTH_LIMIT", "2")):
        return "queue_growth"
    return None


def _select_alternative(vehicle, collision, obstacles, merge):
    alternatives = vehicle.generateAlterPath(collision, obstacles)
    if not alternatives:
        return None
    selected = vehicle.selectBestPath(alternatives)
    if merge:
        change, straight = selected
        vehicle.alter_change_path = change
        return straight
    return selected


def _activate_priority_hold(vehicle, collision, obstacles, merge=False):
    desired = collision["path"]
    selected = _select_alternative(vehicle, collision, obstacles, merge)
    if selected is None:
        _release_priority_hold(vehicle, "no_safe_alternative", collision)
        return False
    vehicle.pathID += 1
    selected.pathID = vehicle.id + "_" + str(vehicle.pathID)
    selected.vehID = vehicle.id
    selected.type = "planned"
    selected.yieldTo = desired.vehID
    vehicle.plannedPath = selected
    vehicle.alter_straight_path = None
    vehicle.status = "yield"
    vehicle.leader = desired.vehID
    vehicle.leadPath = desired
    vehicle.isPathValid = True
    hold = vehicle._mcs_priority_hold
    hold["phase"] = "active"
    hold["activated_at"] = vehicle.simTime
    COUNTS["conditional_hold_activated"] += 1
    diagnostic_trace.record_negotiation(
        vehicle, desired, "priority_hold_activated", accept=True,
        reason="priority_vehicle_can_advance", collision=collision,
        details={"hold_key": hold["key"]})
    diagnostic_trace.record_negotiation(
        vehicle, desired, "applied", accept=True,
        reason="conditional_priority_hold", collision=collision)
    return True


def _refresh_waiting_alternative(vehicle, collision, obstacles, merge):
    desired = collision["path"]
    selected = _select_alternative(vehicle, collision, obstacles, merge)
    if selected is None:
        _release_priority_hold(vehicle, "no_safe_alternative", collision)
        return False
    vehicle.pathID += 1
    selected.pathID = vehicle.id + "_" + str(vehicle.pathID)
    selected.vehID = vehicle.id
    selected.type = "alter"
    selected.yieldTo = desired.vehID
    vehicle.alter_straight_path = selected
    vehicle.waitPath = desired
    COUNTS["conditional_hold_path_refreshed"] += 1
    diagnostic_trace.record_negotiation(
        vehicle, desired, "priority_hold_refreshed", accept=True,
        reason="desired_path_refresh", collision=collision,
        details={"hold_key": vehicle._mcs_priority_hold["key"]})
    return True


def _maintain_priority_hold(vehicle, collisions, obstacles, traci, merge=False):
    """Handle an existing two-stage hold. True suppresses a new negotiation."""
    hold = getattr(vehicle, "_mcs_priority_hold", None)
    if not conditional_priority_hold_enabled() or hold is None:
        return False
    matching = next((entry for entry in collisions
                     if _same_priority_relation(vehicle, entry)), None)
    if matching is None:
        same_priority_elsewhere = any(
            str(entry["path"].vehID) == hold["priority_vehicle"]
            for entry in collisions)
        if same_priority_elsewhere:
            _release_priority_hold(vehicle, "conflict_region_changed")
            return False
        missing_since = hold.setdefault("missing_since", vehicle.simTime)
        if vehicle.simTime - missing_since < 0.3:
            return True
        _release_priority_hold(vehicle, "conflict_disappeared")
        return False
    hold.pop("missing_since", None)
    reason = _release_reason(vehicle, matching, traci, collisions)
    if reason is not None:
        _release_priority_hold(vehicle, reason, matching)
        return False
    if hold["phase"] == "awaiting_agreement":
        if vehicle.waitPath.pathID == matching["path"].pathID:
            return True
        return _refresh_waiting_alternative(vehicle, matching, obstacles, merge)
    if hold["phase"] == "active":
        vehicle.leadPath = matching["path"]
        return True
    can_advance, motion = _priority_motion(
        vehicle, matching["path"], hold["point"], traci, hold)
    if can_advance:
        return _activate_priority_hold(vehicle, matching, obstacles, merge)
    if (vehicle.simTime - hold["last_progress_time"] >= _hold_float(
            "MCS_PRIORITY_HOLD_PROGRESS_TIMEOUT", "4")):
        _release_priority_hold(
            vehicle, "priority_not_progressing", matching, motion)
        return False
    second = int(vehicle.simTime)
    if hold.get("last_pending_log") != second:
        hold["last_pending_log"] = second
        diagnostic_trace.record_negotiation(
            vehicle, matching["path"], "priority_hold_pending", accept=True,
            reason="priority_vehicle_cannot_advance", collision=matching,
            details={"hold_key": hold["key"], **motion})
    return True


def maintain_conditional_priority_hold(
        vehicle, collisions, obstacles, traci, merge=False):
    """Public per-step hook used even when no desired-path collision remains."""
    return _maintain_priority_hold(vehicle, collisions, obstacles, traci, merge)


def complete_conditional_agreement(vehicle, obstacles, traci, merge=False):
    """Finish agreement; return True only when yielding should start now."""
    hold = getattr(vehicle, "_mcs_priority_hold", None)
    if not conditional_priority_hold_enabled() or hold is None:
        return True
    point = hold["point"]
    desired = vehicle.waitPath
    can_advance, motion = _priority_motion(vehicle, desired, point, traci, hold)
    if can_advance:
        hold["phase"] = "active"
        hold["activated_at"] = vehicle.simTime
        COUNTS["conditional_hold_activated"] += 1
        diagnostic_trace.record_negotiation(
            vehicle, desired, "priority_hold_activated", accept=True,
            reason="priority_vehicle_can_advance", details={
                "hold_key": hold["key"], **motion})
        return True
    hold["phase"] = "remembered"
    hold["remembered_at"] = vehicle.simTime
    diagnostic_trace.record_negotiation(
        vehicle, desired, "priority_hold_pending", accept=True,
        reason="agreement_complete_but_priority_blocked", details={
            "hold_key": hold["key"], **motion})
    _clear_agreement_state(vehicle)
    return False


def enabled(vehicle):
    return IMPLEMENTATION == "thesis" and vehicle.alpha in (6, 7)


def planned_update_interval(vehicle, legacy_interval):
    # The simulator/MCM still advances at 0.1 s (Table 5.2).  This is the
    # *candidate trajectory regeneration* expiry, for which the archived
    # implementation uses one second.  Agreement-path validity is separate.
    return 1.0 if enabled(vehicle) else legacy_interval


def following_rate(distance, maximum_speed):
    """Eq. 4.2, bounded by the text's R in [0,1]."""
    if distance < 0 or maximum_speed <= 0:
        raise ValueError("invalid distance or maximum speed")
    if distance <= 5:
        return 1.0
    if distance >= 100:
        return 0.0
    transition = 4 * maximum_speed
    offset = maximum_speed ** 2 / 4
    def curve(x):
        return -.9 / offset ** 2 * (x - (offset + 5)) ** 2 + .9
    value = (curve(distance) if distance <= transition else
             curve(transition) * (100 - distance) / (100 - transition))
    if not 0 <= value <= 1:
        COUNTS["rate_clamped_to_stated_range"] += 1
    return max(0.0, min(1.0, value))


def transmitted_path(path, now, lane_context=None):
    """Publish an independent snapshot of the current 10-second horizon."""
    result = copy.deepcopy(path)
    available = min(len(path.t), len(path.x), len(path.y), len(path.s_d))
    indices = [i for i, t in enumerate(path.t[:available])
               if now - 1e-6 <= t <= now + 10 + 1e-6]
    if not indices:
        raise ValueError("trajectory does not cover publication time")
    start, end = indices[0], indices[-1] + 1
    for name in ("t", "d", "d_d", "d_dd", "d_ddd", "s", "s_d", "s_dd",
                 "s_ddd", "x", "y", "yaw", "ds", "c"):
        values = getattr(path, name, None)
        if hasattr(values, "__len__") and (
            name in ("t", "x", "y", "s_d") or len(values) == len(path.t)
        ):
            setattr(result, name, values[start:end])
    if lane_context:
        for name in ("road_id", "lane_id", "lane_index"):
            setattr(result, name, lane_context.get(name))
    return result


def current_lane_context(vehicle, traci):
    """Read the map-defined lane identity once and keep it on the CAV state.

    SUMO already assigns stable lane IDs in each network file.  The simulation
    adapter exposes those IDs to the otherwise simulator-independent MCM
    packet instead of trying to infer a lane from coordinates.
    """
    context = {
        "road_id": traci.vehicle.getRoadID(vehicle.id),
        "lane_id": traci.vehicle.getLaneID(vehicle.id),
        "lane_index": traci.vehicle.getLaneIndex(vehicle.id),
    }
    vehicle.road = context["road_id"]
    vehicle.lane_id = context["lane_id"]
    vehicle.lane = context["lane_index"]
    return context


def position_at(path, now):
    index = min(range(len(path.t)), key=lambda i: abs(path.t[i] - now))
    return path.x[index], path.y[index]


def arrival_delay(path, point, now):
    """Nearest 2D time sample; unreached finite horizon is +infinity.

    Sampling and unreachable-point handling are implementation assumptions,
    not parameters explicitly defined in the paper.
    """
    indices = [i for i, t in enumerate(path.t) if t >= now - 1e-6]
    if not indices:
        return math.inf
    distances = [(path.x[i] - point[0]) ** 2 + (path.y[i] - point[1]) ** 2
                 for i in indices]
    j = min(range(len(indices)), key=distances.__getitem__)
    if distances[j] > .9 ** 2 and all(
        abs(path.x[k] - path.x[indices[j]]) < 1e-5
        and abs(path.y[k] - path.y[indices[j]]) < 1e-5 for k in indices[j:]
    ):
        return math.inf
    return max(0.0, path.t[indices[j]] - now)


def environmental_term(vehicle, own_path, maximum_speed):
    total = float(own_path.s_d[-1])  # Own vehicle is included with R(0)=1.
    angle = math.radians(vehicle.angle)  # SUMO: clockwise from north.
    forward = (math.sin(angle), math.cos(angle))
    latest = {}
    for path in vehicle.receivedPaths:
        if path.type != "planned" or path.vehID == vehicle.id:
            continue
        previous = latest.get(path.vehID)
        if previous is None or path.t[0] > previous.t[0]:
            latest[path.vehID] = path
    for path in latest.values():
        x, y = position_at(path, vehicle.simTime)
        dx, dy = x - vehicle.pos_x, y - vehicle.pos_y
        longitudinal = dx * forward[0] + dy * forward[1]
        lateral = abs(dx * forward[1] - dy * forward[0])
        # Inherited centerline tolerance; paper does not define lane membership.
        if longitudinal < 0 and lateral < 1.0:
            total += float(path.s_d[-1]) * following_rate(
                math.hypot(dx, dy), maximum_speed)
    return total


def score(vehicle, path, point, maximum_speed, maximum_acceleration):
    horizon = transmitted_path(path, vehicle.simTime)
    dt = arrival_delay(horizon, point, vehicle.simTime)
    environment = environmental_term(vehicle, horizon, maximum_speed)
    performance = .1 * maximum_acceleration if vehicle.alpha == 7 else 0.0
    return {"value": dt - .1 * environment + performance,
            "arrival_delay": dt, "speed_weighted_sum": environment,
            "performance_term": performance}


def send_mcm(vehicle, server, traci):
    """Compute desired TIV at the sender, using only its received MCMs."""
    lane_context = current_lane_context(vehicle, traci)
    vmax = traci.vehicle.getAllowedSpeed(vehicle.id)
    amax = traci.vehicletype.getAccel(vehicle.typeID)
    if vehicle.plannedPath:
        server.append(transmitted_path(
            vehicle.plannedPath, vehicle.simTime, lane_context))
        vehicle.count_send_PT += 1
    for desired in vehicle.desiredPaths or []:
        conflicts, _ = vehicle.checkPathCollision(
            desired, vehicle.receivedPaths, s_type="planned")
        packet = transmitted_path(desired, vehicle.simTime, lane_context)
        packet.tiv_by_receiver = {}
        for conflict in conflicts:
            point = (conflict["collide_x"], conflict["collide_y"])
            value = score(vehicle, desired, point, vmax, amax)
            packet.tiv_by_receiver[str(conflict["collideID"])] = {
                **value, "point": point, "sent_at": vehicle.simTime,
                "sender": vehicle.id, "path_id": desired.pathID}
            COUNTS["sender_tiv_calculations"] += 1
            if not math.isfinite(value["value"]):
                COUNTS["sender_unreached_conflict"] += 1
        if len(packet.tiv_by_receiver) > 1:
            COUNTS["multi_receiver_desired_packets"] += 1
        server.append(packet)
        vehicle.count_send_DT += 1
        COUNTS["desired_packets"] += 1
    if vehicle.alter_straight_path:
        server.append(transmitted_path(
            vehicle.alter_straight_path, vehicle.simTime, lane_context))
        vehicle.count_send_AT += 1


def judge_yield(vehicle, collisions, obstacles, traci, merge=False):
    if _maintain_priority_hold(vehicle, collisions, obstacles, traci, merge):
        return
    desired_ids = [entry["path"].pathID for entry in collisions]
    if vehicle.WithAgreementPhase and vehicle.isWaitAgree:
        if vehicle.waitPath.pathID in desired_ids:
            return
        diagnostic_trace.record_negotiation(
            vehicle, vehicle.waitPath, "cancelled",
            reason="desired_path_disappeared")
        vehicle.isWaitAgree = False
        vehicle.waitAgreeID = []
        vehicle.receiveAgreeID = []
        vehicle.waitPath = None
    for collision in collisions:
        desired = collision["path"]
        if merge:
            if traci.vehicle.getLaneIndex(desired.vehID) == vehicle.lane:
                continue
            if vehicle.pos_x > 300:
                return
        elif traci.vehicle.getRoadID(desired.vehID) == vehicle.road:
            continue
        if desired.pathID in vehicle.yetJudgedList:
            continue
        # The live simulator advances at 0.1 s, but a CAV desired path is
        # valid for one second.  Do not re-negotiate an already decided path
        # during that interval; a new path ID remains immediately eligible.
        if deceleration_prediction.active_decision_is_locked(
                vehicle, desired, vehicle.simTime):
            diagnostic_trace.record_negotiation(
                vehicle, desired, "suppressed", reason="decision_locked",
                collision=collision)
            continue
        diagnostic_trace.record_negotiation(
            vehicle, desired, "started", collision=collision)
        alternatives = vehicle.generateAlterPath(collision, obstacles)
        if not alternatives:
            diagnostic_trace.record_negotiation(
                vehicle, desired, "decision", accept=False,
                reason="no_feasible_alternative", collision=collision)
            vehicle.yetJudgedList.append(desired.pathID)
            vehicle.count_refuse_physics += 1
            COUNTS["no_feasible_alternative"] += 1
            continue
        selected = vehicle.selectBestPath(alternatives)
        if merge:
            vehicle.alter_change_path, vehicle.alter_straight_path = selected
        else:
            vehicle.alter_straight_path = selected
        if not vehicle.alter_straight_path:
            diagnostic_trace.record_negotiation(
                vehicle, desired, "deferred", reason="no_selected_alternative",
                collision=collision)
            continue
        # Shadow mode is intentionally read-only: it observes the same
        # physically feasible alternative considered by the baseline TIV
        # implementation and never changes the decision below.
        deceleration_prediction.record_shadow(
            vehicle, desired, vehicle.alter_straight_path, vehicle.simTime)
        accept = deceleration_prediction.active_decision(
            vehicle, desired, vehicle.alter_straight_path, vehicle.simTime)
        if accept is None:
            received = getattr(desired, "tiv_by_receiver", {}).get(vehicle.id)
            if received is None:
                # No receiver-side fallback; retry on the next MCM.
                diagnostic_trace.record_negotiation(
                    vehicle, desired, "deferred", reason="missing_sender_tiv",
                    collision=collision)
                vehicle.alter_straight_path = None
                COUNTS["missing_sender_tiv"] += 1
                continue
            if received["sender"] != desired.vehID or received["path_id"] != desired.pathID:
                raise ValueError("TIV belongs to a different trajectory")
            planned = score(vehicle, vehicle.plannedPath, received["point"],
                            traci.vehicle.getAllowedSpeed(vehicle.id),
                            traci.vehicletype.getAccel(vehicle.typeID))
            # Fig.4.2 says >=; two unreachable paths are not an arrival-time tie.
            accept = bool(math.isfinite(received["value"])
                          and planned["value"] >= received["value"])
            prediction_method = "thesis-tiv-fallback"
        else:
            # Measure the TIV decision on exactly the same event.  It is
            # audit-only: the proposal decision above remains authoritative.
            received_tiv = getattr(desired, "tiv_by_receiver", {}).get(vehicle.id)
            if received_tiv is not None:
                planned_tiv = score(vehicle, vehicle.plannedPath, received_tiv["point"],
                                    traci.vehicle.getAllowedSpeed(vehicle.id),
                                    traci.vehicletype.getAccel(vehicle.typeID))
                tiv_accept = bool(math.isfinite(received_tiv["value"])
                                  and planned_tiv["value"] >= received_tiv["value"])
                deceleration_prediction.record_tiv_comparison(accept, tiv_accept)
            else:
                deceleration_prediction.COUNTS["tiv_comparison_unavailable"] += 1
            COUNTS["deceleration_active_decisions"] += 1
            planned = {"value": None, "source": "deceleration-propagation"}
            received = {"value": None, "source": "deceleration-propagation"}
            prediction_method = "deceleration-propagation"
        # TIVtep's directly available prediction is the selected sender and
        # receiver MCM trajectory.  Record it for baseline runs and proposal
        # fallbacks; the active proposal has already registered its richer
        # queue prediction above.
        if prediction_method != "deceleration-propagation":
            try:
                tiv_profiles = deceleration_prediction.direct_tiv_profiles(
                    vehicle, desired, vehicle.alter_straight_path,
                    vehicle.simTime, "accept" if accept else "reject")
            except (AttributeError, IndexError, TypeError, ValueError, ZeroDivisionError) as error:
                COUNTS["tiv_prediction_log_unsupported"] += 1
                COUNTS["tiv_prediction_log_error_" + type(error).__name__] += 1
            else:
                evaluation_metrics.register_prediction(
                    vehicle.simTime, "accept" if accept else "reject", 0, tiv_profiles,
                    metadata={
                        "method": prediction_method,
                        "predictor": "selected-transmitted-direct-trajectories",
                        "receiver_id": str(vehicle.id), "sender_id": str(desired.vehID),
                        "desired_path_id": str(desired.pathID),
                        "alternative_path_id": str(vehicle.alter_straight_path.pathID),
                        "actor_vehicle_ids": [str(desired.vehID), str(vehicle.id)],
                        "follower_vehicle_ids": [],
                        "prediction_scope": "sender_receiver_only",
                        "sender_tiv": received.get("value"),
                        "receiver_tiv": planned.get("value"),
                    })
        COUNTS["receiver_tiv_comparisons"] += 1
        COUNTS["accepted" if accept else "rejected"] += 1
        diagnostic_trace.record_negotiation(
            vehicle, desired, "decision", accept=accept,
            reason=prediction_method, collision=collision,
            details={"sender_tiv": received.get("value"),
                     "receiver_tiv": planned.get("value")})
        if len(EXAMPLES) < 100:
            EXAMPLES.append({"receiver": vehicle.id, "sender": desired.vehID,
                             "time": vehicle.simTime, "received": received,
                             "planned": planned, "accept": accept})
        if not accept:
            vehicle.alter_straight_path = None
            vehicle.yetJudgedList.append(desired.pathID)
            vehicle.count_refuse_utility += 1
            continue
        vehicle.count_accept_utility += 1
        vehicle.pathID += 1
        vehicle.alter_straight_path.pathID = vehicle.id + "_" + str(vehicle.pathID)
        vehicle.alter_straight_path.vehID = vehicle.id
        if vehicle.WithAgreementPhase:
            vehicle.alter_straight_path.type = "alter"
            vehicle.alter_straight_path.yieldTo = desired.vehID
            vehicle.waitAgreeID = list(desired.negotiationID)
            vehicle.receiveAgreeID.append(vehicle.id)
            vehicle.isWaitAgree = True
            vehicle.waitPath = desired
            if conditional_priority_hold_enabled():
                _new_priority_hold(vehicle, desired, collision, traci)
            diagnostic_trace.record_negotiation(
                vehicle, desired, "waiting_for_agreement", accept=True,
                reason=prediction_method, collision=collision,
                details={"expected_agreement_ids": vehicle.waitAgreeID,
                         "received_agreement_ids": vehicle.receiveAgreeID})
            return
        vehicle.alter_straight_path.type = "planned"
        vehicle.plannedPath = vehicle.alter_straight_path
        vehicle.alter_straight_path = None
        vehicle.status = "yield"
        vehicle.leader = desired.vehID
        vehicle.leadPath = desired
        vehicle.isPathValid = True
        diagnostic_trace.record_negotiation(
            vehicle, desired, "applied", accept=True,
            reason=prediction_method, collision=collision)


def _write_audit():
    destination = os.environ.get("MCS_TIV_AUDIT")
    if destination:
        def clean(value):
            if hasattr(value, "item"):  # numpy scalar -> Python scalar
                return clean(value.item())
            if isinstance(value, float) and not math.isfinite(value):
                return "unreached"
            if isinstance(value, dict):
                return {key: clean(val) for key, val in value.items()}
            if isinstance(value, (list, tuple)):
                return [clean(val) for val in value]
            return value
        with open(destination, "w") as stream:
            json.dump(clean({"implementation": IMPLEMENTATION,
                             "counts": dict(COUNTS), "examples": EXAMPLES}),
                      stream, indent=2, allow_nan=False)


atexit.register(_write_audit)

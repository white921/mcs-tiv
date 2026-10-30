"""Thesis chapter 4. See docs/thesis-audit.md for numerical assumptions."""
import atexit
import copy
import json
import math
import os
from collections import Counter
import deceleration_prediction
import decision_oracle
import diagnostic_trace
import evaluation_metrics
from trajectory_arrival import arrival_delay as shared_arrival_delay

COUNTS = Counter()
EXAMPLES = []
IMPLEMENTATION = os.environ.get("MCS_TIV_IMPLEMENTATION", "thesis")
if IMPLEMENTATION not in ("thesis", "legacy-local"):
    raise ValueError("invalid MCS_TIV_IMPLEMENTATION")

# Kept opt-in and deliberately narrow: the oracle runner supplies one
# deterministic event ordinal and one forced action.  No priority-hold or
# global policy switch is involved.  The ordinary code path remains byte-for-
# byte equivalent when these variables are absent.
ORACLE_TARGET_EVENT = os.environ.get("MCS_ORACLE_TARGET_EVENT")
ORACLE_FORCE_DECISION = os.environ.get("MCS_ORACLE_FORCE_DECISION")
if ORACLE_TARGET_EVENT is not None:
    ORACLE_TARGET_EVENT = int(ORACLE_TARGET_EVENT)
    if ORACLE_TARGET_EVENT < 1 or ORACLE_FORCE_DECISION not in ("accept", "reject"):
        raise ValueError("oracle target requires a positive event ordinal and accept/reject force")
ORACLE_EVENT_COUNT = 0
ORACLE_BOUNDARY_AUDIT = os.environ.get("MCS_ORACLE_BOUNDARY_AUDIT")
ORACLE_EXPECTED_FINGERPRINT = os.environ.get("MCS_ORACLE_EXPECTED_FINGERPRINT")
_ORACLE_CONTEXT_PROVIDER = None


def configure_oracle_context_provider(provider):
    """Install the Eval.3 controller-state witness used by oracle branches."""
    global _ORACLE_CONTEXT_PROVIDER
    _ORACLE_CONTEXT_PROVIDER = provider


def _write_oracle_boundary(request, forced_choice):
    if _ORACLE_CONTEXT_PROVIDER is None:
        raise RuntimeError("decision oracle context provider is not configured")
    context = _ORACLE_CONTEXT_PROVIDER(request["manifest"])
    fingerprint = decision_oracle.canonical_hash(context)
    if (ORACLE_EXPECTED_FINGERPRINT is not None
            and fingerprint != ORACLE_EXPECTED_FINGERPRINT):
        raise ValueError("decision oracle boundary fingerprint mismatch")
    record = {
        "schema": "decision-oracle-boundary-v1",
        "fingerprint": fingerprint,
        "request": request["manifest"],
        "yamashita_choice": request["yamashita_choice"],
        "proposal_choice": request["proposal_choice"],
        "forced_choice": forced_choice,
    }
    if ORACLE_BOUNDARY_AUDIT:
        destination = os.path.abspath(ORACLE_BOUNDARY_AUDIT)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        temporary = destination + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
        os.replace(temporary, destination)
    return record


def apply_decision(request, choice):
    """Apply one already-evaluated negotiation choice exactly once."""
    if request.get("applied"):
        raise RuntimeError("negotiation request applied twice")
    if choice not in ("accept", "reject"):
        raise ValueError("negotiation choice must be accept or reject")
    request["applied"] = True
    return choice


def apply_negotiation_request(request, choice):
    """Apply the sole mutable half of a prepared negotiation request."""
    choice = apply_decision(request, choice)
    vehicle = request["vehicle"]
    desired = request["desired"]
    collision = request["collision"]
    received = request["received"]
    planned = request["planned"]
    prediction_method = request["prediction_method"]
    accept = choice == "accept"
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
        return "rejected"
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
        diagnostic_trace.record_negotiation(
            vehicle, desired, "waiting_for_agreement", accept=True,
            reason=prediction_method, collision=collision,
            details={"expected_agreement_ids": vehicle.waitAgreeID,
                     "received_agreement_ids": vehicle.receiveAgreeID})
        return "waiting_for_agreement"
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
    return "applied"


def enabled(vehicle):
    return IMPLEMENTATION == "thesis" and vehicle.alpha in (6, 7)


def planned_update_interval(vehicle, legacy_interval):
    # The simulator/MCM still advances at 0.1 s (Table 5.2).  This is the
    # *candidate trajectory regeneration* expiry, for which the archived
    # implementation uses one second.  Agreement-path validity is separate.
    return 1.0 if enabled(vehicle) else legacy_interval


def trajectories_are_too_close(
        own_x, own_y, other_x, other_y,
        own_dx, own_dy, other_dx, other_dy,
        vehicle_length, vehicle_width, headway):
    """Check proximity using the longitudinal axis of this four-way map."""
    if abs(own_y) > 3.2:
        longitudinal_gap = abs(own_y - other_y)
        lateral_gap = abs(own_x - other_x)
        following_speed = max(abs(own_dy), abs(other_dy))
    else:
        longitudinal_gap = abs(own_x - other_x)
        lateral_gap = abs(own_y - other_y)
        following_speed = max(abs(own_dx), abs(other_dx))
    return (
        longitudinal_gap < max(vehicle_length, following_speed * headway)
        and lateral_gap < vehicle_width
    )


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
        for name in ("road_id", "lane_id", "lane_index", "lane_position",
                     "allowed_speed_mps"):
            setattr(result, name, lane_context.get(name))
    return result


def current_lane_context(vehicle, traci):
    """Read the map-defined lane identity once and keep it on the CAV state.

    SUMO already assigns stable lane IDs in each network file.  The simulation
    adapter exposes those IDs to the otherwise simulator-independent MCM
    packet instead of trying to infer a lane from coordinates.
    """
    road_allowed_speed = float(traci.vehicle.getAllowedSpeed(vehicle.id))
    try:
        vehicle_max_speed = float(traci.vehicletype.getMaxSpeed(vehicle.typeID))
    except (AttributeError, TypeError, ValueError):
        vehicle_max_speed = road_allowed_speed
    allowed_speed = min(road_allowed_speed, vehicle_max_speed)
    if not math.isfinite(allowed_speed) or allowed_speed <= 0:
        allowed_speed = None
    context = {
        "road_id": traci.vehicle.getRoadID(vehicle.id),
        "lane_id": traci.vehicle.getLaneID(vehicle.id),
        "lane_index": traci.vehicle.getLaneIndex(vehicle.id),
        "lane_position": traci.vehicle.getLanePosition(vehicle.id),
        "allowed_speed_mps": allowed_speed,
    }
    vehicle.road = context["road_id"]
    vehicle.lane_id = context["lane_id"]
    vehicle.lane = context["lane_index"]
    vehicle.lane_position = context["lane_position"]
    vehicle.allowed_speed_mps = context["allowed_speed_mps"]
    return context


def position_at(path, now):
    index = min(range(len(path.t)), key=lambda i: abs(path.t[i] - now))
    return path.x[index], path.y[index]


def arrival_delay(path, point, now):
    """Nearest 2D time sample; unreached finite horizon is +infinity.

    Sampling and unreachable-point handling are implementation assumptions,
    not parameters explicitly defined in the paper.
    """
    return shared_arrival_delay(path, point, now)


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
    vmax = lane_context["allowed_speed_mps"]
    if vmax is None:
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
    global ORACLE_EVENT_COUNT
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
        received_packet = getattr(desired, "tiv_by_receiver", {}).get(
            str(vehicle.id)) or getattr(desired, "tiv_by_receiver", {}).get(
                vehicle.id)
        if "collide_x" in collision and "collide_y" in collision:
            point = (collision["collide_x"], collision["collide_y"])
        else:
            point = (received_packet or {}).get("point")
        deceleration_prediction.record_shadow(
            vehicle, desired, vehicle.alter_straight_path, vehicle.simTime,
            point)
        accept = deceleration_prediction.active_decision(
            vehicle, desired, vehicle.alter_straight_path, vehicle.simTime,
            point)
        yamashita_accept = None
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
            yamashita_accept = accept
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
                yamashita_accept = tiv_accept
                deceleration_prediction.record_tiv_comparison(accept, tiv_accept)
            else:
                deceleration_prediction.COUNTS["tiv_comparison_unavailable"] += 1
            COUNTS["deceleration_active_decisions"] += 1
            planned = {"value": None, "source": "deceleration-propagation"}
            received = {"value": None, "source": "deceleration-propagation"}
            prediction_method = "deceleration-propagation"
        target_event = ORACLE_TARGET_EVENT == ORACLE_EVENT_COUNT + 1
        proposal_choice = None
        if target_event:
            try:
                proposal_evaluation = deceleration_prediction.evaluate(
                    vehicle, desired, vehicle.alter_straight_path,
                    vehicle.simTime, point)
            except (AttributeError, IndexError, TypeError, ValueError,
                    ZeroDivisionError):
                proposal_evaluation = None
            if proposal_evaluation is not None:
                proposal_choice = proposal_evaluation.get("decision")
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
        ORACLE_EVENT_COUNT += 1
        request = {
            "ordinal": ORACLE_EVENT_COUNT,
            "time": float(vehicle.simTime),
            "receiver": str(vehicle.id),
            "sender": str(desired.vehID),
            "desired_path_id": str(desired.pathID),
            "alternative_path_id": str(getattr(
                vehicle.alter_straight_path, "pathID", None)),
            "vehicle": vehicle,
            "desired": desired,
            "collision": collision,
            "received": received,
            "planned": planned,
            "prediction_method": prediction_method,
            "yamashita_choice": ("accept" if yamashita_accept else "reject"
                                  if yamashita_accept is not None else None),
            "proposal_choice": proposal_choice,
            "applied": False,
        }
        request["manifest"] = {
            key: request[key] for key in (
                "ordinal", "time", "receiver", "sender", "desired_path_id",
                "alternative_path_id")
        }
        choice = "accept" if accept else "reject"
        # The branch replay reaches this boundary from the same previous-step
        # checkpoint.  The complete context fingerprint must match before the
        # selected event alone may be forced.
        if target_event:
            choice = ORACLE_FORCE_DECISION
            request["prediction_method"] = "decision-oracle-forced-" + choice
            _write_oracle_boundary(request, choice)
        outcome = apply_negotiation_request(request, choice)
        if outcome == "rejected":
            continue
        if outcome == "waiting_for_agreement":
            return


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

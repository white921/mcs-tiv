"""Thesis chapter 4. See docs/thesis-audit.md for numerical assumptions."""
import atexit
import copy
import json
import math
import os
from collections import Counter

COUNTS = Counter()
EXAMPLES = []
IMPLEMENTATION = os.environ.get("MCS_TIV_IMPLEMENTATION", "thesis")
if IMPLEMENTATION not in ("thesis", "legacy-local"):
    raise ValueError("invalid MCS_TIV_IMPLEMENTATION")


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


def transmitted_path(path, now):
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
    return result


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
    vmax = traci.vehicle.getAllowedSpeed(vehicle.id)
    amax = traci.vehicletype.getAccel(vehicle.typeID)
    if vehicle.plannedPath:
        server.append(transmitted_path(vehicle.plannedPath, vehicle.simTime))
        vehicle.count_send_PT += 1
    for desired in vehicle.desiredPaths or []:
        conflicts, _ = vehicle.checkPathCollision(
            desired, vehicle.receivedPaths, s_type="planned")
        packet = transmitted_path(desired, vehicle.simTime)
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
        server.append(transmitted_path(vehicle.alter_straight_path, vehicle.simTime))
        vehicle.count_send_AT += 1


def judge_yield(vehicle, collisions, obstacles, traci, merge=False):
    desired_ids = [entry["path"].pathID for entry in collisions]
    if vehicle.WithAgreementPhase and vehicle.isWaitAgree:
        if vehicle.waitPath.pathID in desired_ids:
            return
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
        alternatives = vehicle.generateAlterPath(collision, obstacles)
        if not alternatives:
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
            continue
        received = getattr(desired, "tiv_by_receiver", {}).get(vehicle.id)
        if received is None:
            # No receiver-side fallback; retry on the next MCM.
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
        COUNTS["receiver_tiv_comparisons"] += 1
        COUNTS["accepted" if accept else "rejected"] += 1
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
            return
        vehicle.alter_straight_path.type = "planned"
        vehicle.plannedPath = vehicle.alter_straight_path
        vehicle.alter_straight_path = None
        vehicle.status = "yield"
        vehicle.leader = desired.vehID
        vehicle.leadPath = desired
        vehicle.isPathValid = True


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

"""Optional JSONL traces for replaying and diagnosing Eval.3 runs.

The trace functions are no-ops unless their corresponding environment
variables are set.  They observe live state only and never mutate a vehicle,
trajectory, negotiation, or TraCI setting.
"""
from __future__ import annotations

import atexit
import json
import math
import os
from pathlib import Path


SCHEMA_VERSION = 2
STATE_AUDIT = os.environ.get("MCS_VEHICLE_STATE_AUDIT")
CONFLICT_AUDIT = os.environ.get("MCS_CONFLICT_AUDIT")
NEGOTIATION_AUDIT = os.environ.get("MCS_NEGOTIATION_AUDIT")
RUNTIME_AUDIT = os.environ.get("MCS_RUNTIME_AUDIT")

_STREAMS = {}
_WRITES = {}


def initialize():
    """Create every configured trace file, including zero-event streams."""
    for destination in (STATE_AUDIT, CONFLICT_AUDIT, NEGOTIATION_AUDIT,
                        RUNTIME_AUDIT):
        if not destination or destination in _STREAMS:
            continue
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        _STREAMS[destination] = path.open("w", encoding="utf-8")
        _WRITES[destination] = 0


def _clean(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _clean(value.item())
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(item) for item in value]
    return str(value)


def _write(destination, record):
    if not destination:
        return
    stream = _STREAMS.get(destination)
    if stream is None:
        initialize()
        stream = _STREAMS[destination]
    stream.write(json.dumps(_clean({"schema_version": SCHEMA_VERSION, **record}),
                            ensure_ascii=False, separators=(",", ":")) + "\n")
    _WRITES[destination] += 1
    # At the 0.1 s simulation cadence this flushes roughly once per second.
    if _WRITES[destination] % 10 == 0:
        stream.flush()


def _safe(callable_, default=None):
    try:
        return callable_()
    except Exception:
        return default


def _path_id(path):
    return getattr(path, "pathID", None) if path is not None else None


def decode_vehicle_signals(signal_bits):
    """Return stable names for SUMO's vehicle signal bitset.

    Keeping both the original integer and decoded flags makes the trace usable
    by SUMO-oriented tools as well as by the local replay viewer.
    """
    if signal_bits is None:
        return None
    signal_bits = int(signal_bits)
    return {
        "right_blinker": bool(signal_bits & 1),
        "left_blinker": bool(signal_bits & 2),
        "emergency_blinker": bool(signal_bits & 4),
        "brake_light": bool(signal_bits & 8),
        "front_light": bool(signal_bits & 16),
        "fog_light": bool(signal_bits & 32),
        "high_beam": bool(signal_bits & 64),
        "reverse_light": bool(signal_bits & 128),
        "wiper": bool(signal_bits & 256),
        "left_door_open": bool(signal_bits & 512),
        "right_door_open": bool(signal_bits & 1024),
    }


def record_vehicle_states(vehicles, sim_time, traci):
    """Write one frame containing every active vehicle's observable state."""
    if not STATE_AUDIT:
        return
    states = []
    for vehicle in vehicles:
        vehicle_id = str(vehicle.id)
        leader = _safe(lambda: traci.vehicle.getLeader(vehicle_id))
        desired = getattr(vehicle, "desiredPaths", None) or []
        signal_bits = _safe(lambda: traci.vehicle.getSignals(vehicle_id))
        states.append({
            "vehicle_id": vehicle_id,
            "vehicle_group": getattr(vehicle, "type", None),
            "vehicle_type_id": getattr(vehicle, "typeID", None),
            "x": float(vehicle.pos_x),
            "y": float(vehicle.pos_y),
            "speed_mps": float(vehicle.speed),
            "allowed_speed_mps": _safe(
                lambda: float(traci.vehicle.getAllowedSpeed(vehicle_id))),
            "accel_mps2": float(vehicle.accel),
            "angle_deg": _safe(lambda: float(traci.vehicle.getAngle(vehicle_id))),
            "slope_deg": _safe(lambda: float(traci.vehicle.getSlope(vehicle_id))),
            "length_m": _safe(lambda: float(traci.vehicle.getLength(vehicle_id)),
                              float(getattr(vehicle, "length", 5.0))),
            "width_m": _safe(lambda: float(traci.vehicle.getWidth(vehicle_id)),
                             float(getattr(vehicle, "width", 1.8))),
            "height_m": _safe(lambda: float(traci.vehicle.getHeight(vehicle_id))),
            "lane_position_m": _safe(
                lambda: float(traci.vehicle.getLanePosition(vehicle_id))),
            "lateral_lane_position_m": _safe(
                lambda: float(traci.vehicle.getLateralLanePosition(vehicle_id))),
            "signals": int(signal_bits) if signal_bits is not None else None,
            "signal_state": decode_vehicle_signals(signal_bits),
            "color_rgba": _safe(lambda: list(traci.vehicle.getColor(vehicle_id))),
            "route_id": getattr(vehicle, "route", None),
            "road_id": getattr(vehicle, "road", None),
            "lane_index": getattr(vehicle, "lane", None),
            "lane_id": _safe(lambda: traci.vehicle.getLaneID(vehicle_id)),
            "leader_id": str(leader[0]) if leader else None,
            "leader_gap_m": float(leader[1]) if leader else None,
            "controller_status": getattr(vehicle, "status", None),
            "junction_status": getattr(vehicle, "passjunctionstatus", None),
            "planned_path_id": _path_id(getattr(vehicle, "plannedPath", None)),
            "desired_path_ids": [_path_id(path) for path in desired],
            "leader_path_id": _path_id(getattr(vehicle, "leadPath", None)),
            "waiting_for_agreement": bool(getattr(vehicle, "isWaitAgree", False)),
            "wait_path_id": _path_id(getattr(vehicle, "waitPath", None)),
            "expected_agreement_ids": list(getattr(vehicle, "waitAgreeID", []) or []),
            "received_agreement_ids": list(getattr(vehicle, "receiveAgreeID", []) or []),
        })
    _write(STATE_AUDIT, {"record_type": "vehicle_state_frame",
                         "sim_time": float(sim_time), "vehicles": states})


def record_conflict(vehicle, own_path, other_path, collision, traci,
                    own_pass_time=None, other_pass_time=None, pet_s=None,
                    reason=None, check_type=None):
    """Record a positive trajectory-conflict decision and its live context."""
    if not CONFLICT_AUDIT:
        return
    other_id = str(getattr(other_path, "vehID", "unknown"))
    other_position = _safe(lambda: traci.vehicle.getPosition(other_id))
    conflict_point = (collision.get("collide_x"), collision.get("collide_y"))
    ego_distance = None
    other_distance = None
    if None not in conflict_point:
        ego_distance = math.hypot(
            float(vehicle.pos_x) - conflict_point[0],
            float(vehicle.pos_y) - conflict_point[1])
        if other_position is not None:
            other_distance = math.hypot(
                other_position[0] - conflict_point[0],
                other_position[1] - conflict_point[1])
    _write(CONFLICT_AUDIT, {
        "record_type": "conflict_detected",
        "sim_time": float(vehicle.simTime),
        "check_type": check_type,
        "reason": reason,
        "ego_vehicle_id": str(vehicle.id),
        "other_vehicle_id": other_id,
        "ego_route_id": getattr(vehicle, "route", None),
        "other_route_id": _safe(lambda: traci.vehicle.getRouteID(other_id)),
        "ego_road_id": getattr(vehicle, "road", None),
        "other_road_id": _safe(lambda: traci.vehicle.getRoadID(other_id)),
        "other_lane_id": _safe(lambda: traci.vehicle.getLaneID(other_id)),
        "other_speed_mps": _safe(lambda: traci.vehicle.getSpeed(other_id)),
        "ego_position": [float(vehicle.pos_x), float(vehicle.pos_y)],
        "other_position": list(other_position) if other_position is not None else None,
        "ego_junction_status": getattr(vehicle, "passjunctionstatus", None),
        "own_path_id": _path_id(own_path),
        "own_path_type": getattr(own_path, "type", None),
        "other_path_id": _path_id(other_path),
        "other_path_type": getattr(other_path, "type", None),
        "own_path_start_time": (own_path.t[0] if getattr(own_path, "t", None) else None),
        "other_path_start_time": (other_path.t[0] if getattr(other_path, "t", None) else None),
        "conflict_point": list(conflict_point),
        "ego_distance_to_conflict_m": ego_distance,
        "other_distance_to_conflict_m": other_distance,
        "predicted_own_pass_time": own_pass_time,
        "predicted_other_pass_time": other_pass_time,
        "pet_s": pet_s,
        "duration_s": collision.get("duration"),
    })


def record_negotiation(vehicle, desired, event, *, accept=None, reason=None,
                       collision=None, details=None):
    """Write one receiver-side negotiation lifecycle event."""
    if not NEGOTIATION_AUDIT:
        return
    collision = collision or {}
    _write(NEGOTIATION_AUDIT, {
        "record_type": "negotiation_event",
        "sim_time": float(vehicle.simTime),
        "event": event,
        "reason": reason,
        "accept": accept,
        "receiver_id": str(vehicle.id),
        "sender_id": str(getattr(desired, "vehID", "unknown")),
        "desired_path_id": _path_id(desired),
        "negotiation_vehicle_ids": list(getattr(desired, "negotiationID", []) or []),
        "conflict_point": [collision.get("collide_x"), collision.get("collide_y")]
                          if collision else None,
        "receiver_position": [float(vehicle.pos_x), float(vehicle.pos_y)],
        "receiver_route_id": getattr(vehicle, "route", None),
        "receiver_road_id": getattr(vehicle, "road", None),
        "receiver_junction_status": getattr(vehicle, "passjunctionstatus", None),
        "alternative_path_id": _path_id(getattr(vehicle, "alter_straight_path", None)),
        "details": details or {},
    })


def record_runtime(sim_time, phase_seconds, vehicle_count, total_seconds):
    """Write per-step wall-clock costs without affecting simulation state."""
    if not RUNTIME_AUDIT:
        return
    _write(RUNTIME_AUDIT, {
        "record_type": "runtime_step",
        "sim_time": float(sim_time),
        "vehicle_count": int(vehicle_count),
        "total_seconds": float(total_seconds),
        "phase_seconds": {name: float(value) for name, value in phase_seconds.items()},
    })


def close():
    for stream in _STREAMS.values():
        stream.flush()
        stream.close()
    _STREAMS.clear()
    _WRITES.clear()


atexit.register(close)

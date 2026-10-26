"""Online metrics shared by the baseline and deceleration-propagation runs."""
from __future__ import annotations

import atexit
import json
import math
import os
from collections import Counter, defaultdict

DT = 0.1
# Fallbacks are used only when a runner cannot query SUMO.  Normal experiment
# runs pass each vehicle's current allowed speed, which already incorporates
# its lane and vehicle-type limits.
CAR_FREE_FLOW_SPEED = 13.89
BUS_FREE_FLOW_SPEED = 11.11
HARD_BRAKE = -3.0
STOP_SPEED = 0.1
AUDIT = os.environ.get("MCS_EVALUATION_AUDIT")
PREDICTION_EVENT_AUDIT = os.environ.get("MCS_PREDICTION_EVENT_AUDIT")

COUNTS = Counter()
GROUPS = defaultdict(Counter)
VEHICLES = {}
FOLLOWING_VEHICLES = {}
PENDING = []
PREDICTION = defaultdict(Counter)
PREDICTION_EVENTS = []


def _group(vehicle):
    return "bus" if getattr(vehicle, "type", "Car") == "Bus" else "car"


def _reference_speed(vehicle, vehicle_id, allowed_speeds):
    """Return the per-sample attainable free-flow speed in m/s.

    A fixed 13.89 m/s reference incorrectly charged buses (whose configured
    maximum is 11.11 m/s) even when they travelled freely.  SUMO's allowed
    speed is the relevant reference because it includes both the current road
    limit and the vehicle type's own maximum speed.
    """
    value = (allowed_speeds or {}).get(vehicle_id)
    if value is not None and math.isfinite(float(value)) and float(value) > 0:
        return float(value)
    return BUS_FREE_FLOW_SPEED if _group(vehicle) == "bus" else CAR_FREE_FLOW_SPEED


def observe(vehicles, now, allowed_speeds=None):
    """Collect actual 0.1-second states and finish due prediction windows."""
    if not AUDIT:
        return
    current = {str(vehicle.id): vehicle for vehicle in vehicles}
    for vehicle_id, vehicle in current.items():
        speed = float(vehicle.speed)
        accel = float(vehicle.accel)
        group = _group(vehicle)
        reference_speed = _reference_speed(vehicle, vehicle_id, allowed_speeds)
        shortfall = max(0.0, reference_speed - speed) * DT
        net_distance_delta = (speed - reference_speed) * DT
        aggregate = GROUPS[group]
        aggregate["samples"] += 1
        aggregate["speed_sum"] += speed
        aggregate["distance_m"] += speed * DT
        aggregate["hard_brake_time_s"] += DT if accel <= HARD_BRAKE else 0
        aggregate["stop_time_s"] += DT if speed < STOP_SPEED else 0
        aggregate["reference_speed_sum"] += reference_speed
        aggregate["free_flow_shortfall_m"] += shortfall
        aggregate["net_free_flow_distance_delta_m"] += net_distance_delta
        item = VEHICLES.setdefault(vehicle_id, {"group": group, "samples": 0,
                                                 "speed_sum": 0.0, "distance_m": 0.0,
                                                 "hard_brake_time_s": 0.0,
                                                 "stop_time_s": 0.0,
                                                 "reference_speed_sum": 0.0,
                                                 "free_flow_shortfall_m": 0.0,
                                                 "net_free_flow_distance_delta_m": 0.0})
        item["samples"] += 1
        item["speed_sum"] += speed
        item["distance_m"] += speed * DT
        item["hard_brake_time_s"] += DT if accel <= HARD_BRAKE else 0
        item["stop_time_s"] += DT if speed < STOP_SPEED else 0
        item["reference_speed_sum"] += reference_speed
        item["free_flow_shortfall_m"] += shortfall
        item["net_free_flow_distance_delta_m"] += net_distance_delta
        # This is a method-independent follower proxy: both the baseline and
        # proposal expose ``leader`` through the live CAV controller.
        if getattr(vehicle, "leader", None):
            follower = FOLLOWING_VEHICLES.setdefault(vehicle_id, {"group": group, "samples": 0,
                                                                    "reference_speed_sum": 0.0,
                                                                    "free_flow_shortfall_m": 0.0,
                                                                    "net_free_flow_distance_delta_m": 0.0,
                                                                    "hard_brake_time_s": 0.0,
                                                                    "stop_time_s": 0.0})
            follower["samples"] += 1
            follower["reference_speed_sum"] += reference_speed
            follower["free_flow_shortfall_m"] += shortfall
            follower["net_free_flow_distance_delta_m"] += net_distance_delta
            follower["hard_brake_time_s"] += DT if accel <= HARD_BRAKE else 0
            follower["stop_time_s"] += DT if speed < STOP_SPEED else 0

    remaining = []
    for event in PENDING:
        if now <= event["end"] + 1e-6:
            index = int(round((now - event["start"]) / DT))
            if 0 <= index <= 100:
                for vehicle_id, profile in event["profiles"].items():
                    vehicle = current.get(vehicle_id)
                    if vehicle is None:
                        continue
                    error = float(vehicle.speed) - profile.speeds[index]
                    vehicle_event = event["vehicles"][vehicle_id]
                    vehicle_event["actual_speed_mps"][index] = float(vehicle.speed)
                    vehicle_event["samples"] += 1
                    vehicle_event["absolute_error"] += abs(error)
                    vehicle_event["squared_error"] += error * error
                    vehicle_event["actual_distance_m"] += float(vehicle.speed) * DT
                    vehicle_event["predicted_distance_m"] += profile.speeds[index] * DT
                    event["samples"] += 1
                    event["absolute_error"] += abs(error)
                    event["squared_error"] += error * error
                    event["actual_distance_m"] += float(vehicle.speed) * DT
                    event["predicted_distance_m"] += profile.speeds[index] * DT
        if now >= event["end"] - 1e-6:
            _finish_prediction(event)
        else:
            remaining.append(event)
    PENDING[:] = remaining


def register_prediction(start, decision, follower_count, profiles, metadata=None):
    """Queue a chosen 10-second prediction and retain its measured outcome.

    ``metadata`` is deliberately method-neutral.  It lets TIVtep and the
    proposed method write one comparable event schema while preserving which
    vehicles each method actually predicted.
    """
    if not AUDIT:
        return
    vehicles = {}
    for vehicle_id, profile in profiles.items():
        vehicles[vehicle_id] = {
            "predicted_speed_mps": list(profile.speeds),
            "actual_speed_mps": [None] * len(profile.speeds),
            "samples": 0, "absolute_error": 0.0, "squared_error": 0.0,
            "actual_distance_m": 0.0, "predicted_distance_m": 0.0,
        }
    PENDING.append({"start": float(start), "end": round(float(start) + 10.0, 3),
                    "decision": decision, "follower_count": follower_count,
                    "profiles": profiles, "samples": 0, "absolute_error": 0.0,
                    "squared_error": 0.0, "actual_distance_m": 0.0,
                    "predicted_distance_m": 0.0, "metadata": dict(metadata or {}),
                    "vehicles": vehicles})
    COUNTS["prediction_windows"] += 1


def _finish_prediction(event, complete=True):
    if not event["samples"]:
        COUNTS["prediction_windows_without_samples"] += 1
        return
    if complete:
        bucket = PREDICTION["all"]
        decision_bucket = PREDICTION[event["decision"]]
        for target in (bucket, decision_bucket):
            target["windows"] += 1
            target["samples"] += event["samples"]
            target["absolute_error"] += event["absolute_error"]
            target["squared_error"] += event["squared_error"]
            target["distance_error_m"] += abs(event["actual_distance_m"] - event["predicted_distance_m"])
            target["followers"] += event["follower_count"]
    else:
        COUNTS["prediction_windows_partial_at_simulation_end"] += 1
    # Keep the raw 0.1-second series too.  Aggregate MAE/RMSE answers whether
    # a method is accurate on average; this event log exposes *which* decision
    # and which vehicle made it inaccurate.
    vehicles = {}
    for vehicle_id, item in event["vehicles"].items():
        samples = item["samples"]
        vehicles[vehicle_id] = {
            "predicted_speed_mps": item["predicted_speed_mps"],
            "actual_speed_mps": item["actual_speed_mps"],
            "samples": samples,
            "speed_mae_mps": item["absolute_error"] / samples if samples else None,
            "speed_rmse_mps": math.sqrt(item["squared_error"] / samples) if samples else None,
            "actual_distance_m": item["actual_distance_m"],
            "predicted_distance_m": item["predicted_distance_m"],
            "distance_error_m": abs(item["actual_distance_m"] - item["predicted_distance_m"]),
        }
    PREDICTION_EVENTS.append({
        "start": event["start"], "end": event["end"],
        "horizon_complete": complete,
        "decision": event["decision"], "follower_count": event["follower_count"],
        "metadata": event["metadata"], "vehicles": vehicles,
    })


def _distribution(values):
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    percentile = lambda q: ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]
    return {"count": len(ordered), "mean": sum(ordered) / len(ordered),
            "median": percentile(.5), "p95": percentile(.95), "max": ordered[-1]}


def _normalise_prediction(bucket):
    if not bucket["samples"]:
        return {"windows": 0}
    return {"windows": bucket["windows"], "samples": bucket["samples"],
            "speed_mae_mps": bucket["absolute_error"] / bucket["samples"],
            "speed_rmse_mps": math.sqrt(bucket["squared_error"] / bucket["samples"]),
            "mean_abs_distance_error_m_per_window": bucket["distance_error_m"] / bucket["windows"],
            "mean_followers_per_window": bucket["followers"] / bucket["windows"]}


def _write_audit():
    if not AUDIT:
        return
    # Preserve decisions made in the final ten seconds as explicitly partial
    # event records.  They must not be mixed into the 10-second aggregate.
    for event in PENDING:
        _finish_prediction(event, complete=False)
    PENDING.clear()
    groups = {}
    for name, data in GROUPS.items():
        groups[name] = {**data,
                        "mean_speed_mps": data["speed_sum"] / data["samples"] if data["samples"] else None,
                        "mean_reference_speed_mps": data["reference_speed_sum"] / data["samples"] if data["samples"] else None}
    by_group = defaultdict(list)
    net_by_group = defaultdict(list)
    following_by_group = defaultdict(list)
    following_net_by_group = defaultdict(list)
    for data in VEHICLES.values():
        by_group[data["group"]].append(data["free_flow_shortfall_m"])
        net_by_group[data["group"]].append(data["net_free_flow_distance_delta_m"])
    for data in FOLLOWING_VEHICLES.values():
        following_by_group[data["group"]].append(data["free_flow_shortfall_m"])
        following_net_by_group[data["group"]].append(data["net_free_flow_distance_delta_m"])
    result = {"thresholds": {"hard_brake_mps2": HARD_BRAKE, "stop_speed_mps": STOP_SPEED,
                               "free_flow_reference": "SUMO allowed speed per vehicle and time step",
                               "fallback_car_mps": CAR_FREE_FLOW_SPEED,
                               "fallback_bus_mps": BUS_FREE_FLOW_SPEED},
              "counts": dict(COUNTS), "groups": groups,
              "vehicle_free_flow_shortfall_m": {name: _distribution(values) for name, values in by_group.items()},
              "vehicle_free_flow_shortfall_samples_m": dict(by_group),
              "vehicle_net_free_flow_distance_delta_m": {name: _distribution(values) for name, values in net_by_group.items()},
              "vehicle_net_free_flow_distance_delta_samples_m": dict(net_by_group),
              "following_vehicle_free_flow_shortfall_m": {name: _distribution(values) for name, values in following_by_group.items()},
              "following_vehicle_free_flow_shortfall_samples_m": dict(following_by_group),
              "following_vehicle_net_free_flow_distance_delta_m": {name: _distribution(values) for name, values in following_net_by_group.items()},
              "following_vehicle_net_free_flow_distance_delta_samples_m": dict(following_net_by_group),
              "prediction_accuracy": {name: _normalise_prediction(data) for name, data in PREDICTION.items()},
              "prediction_accuracy_raw": {name: dict(data) for name, data in PREDICTION.items()}}
    with open(AUDIT, "w") as stream:
        json.dump(result, stream, indent=2)
    if PREDICTION_EVENT_AUDIT:
        with open(PREDICTION_EVENT_AUDIT, "w") as stream:
            for event in PREDICTION_EVENTS:
                stream.write(json.dumps(event) + "\n")


atexit.register(_write_audit)

"""Online metrics shared by the baseline and deceleration-propagation runs."""
from __future__ import annotations

import atexit
import json
import math
import os
from collections import Counter, defaultdict

DT = 0.1
FREE_FLOW_SPEED = 13.89
HARD_BRAKE = -3.0
STOP_SPEED = 0.1
AUDIT = os.environ.get("MCS_EVALUATION_AUDIT")

COUNTS = Counter()
GROUPS = defaultdict(Counter)
VEHICLES = {}
FOLLOWING_VEHICLES = {}
PENDING = []
PREDICTION = defaultdict(Counter)


def _group(vehicle):
    return "bus" if getattr(vehicle, "type", "Car") == "Bus" else "car"


def observe(vehicles, now):
    """Collect actual 0.1-second states and finish due prediction windows."""
    if not AUDIT:
        return
    current = {str(vehicle.id): vehicle for vehicle in vehicles}
    for vehicle_id, vehicle in current.items():
        speed = float(vehicle.speed)
        accel = float(vehicle.accel)
        group = _group(vehicle)
        aggregate = GROUPS[group]
        aggregate["samples"] += 1
        aggregate["speed_sum"] += speed
        aggregate["distance_m"] += speed * DT
        aggregate["hard_brake_time_s"] += DT if accel <= HARD_BRAKE else 0
        aggregate["stop_time_s"] += DT if speed < STOP_SPEED else 0
        item = VEHICLES.setdefault(vehicle_id, {"group": group, "samples": 0,
                                                 "speed_sum": 0.0, "distance_m": 0.0,
                                                 "hard_brake_time_s": 0.0,
                                                 "stop_time_s": 0.0,
                                                 "free_flow_shortfall_m": 0.0})
        item["samples"] += 1
        item["speed_sum"] += speed
        item["distance_m"] += speed * DT
        item["hard_brake_time_s"] += DT if accel <= HARD_BRAKE else 0
        item["stop_time_s"] += DT if speed < STOP_SPEED else 0
        item["free_flow_shortfall_m"] += max(0.0, FREE_FLOW_SPEED - speed) * DT
        # This is a method-independent follower proxy: both the baseline and
        # proposal expose ``leader`` through the live CAV controller.
        if getattr(vehicle, "leader", None):
            follower = FOLLOWING_VEHICLES.setdefault(vehicle_id, {"group": group, "samples": 0,
                                                                    "free_flow_shortfall_m": 0.0,
                                                                    "hard_brake_time_s": 0.0,
                                                                    "stop_time_s": 0.0})
            follower["samples"] += 1
            follower["free_flow_shortfall_m"] += max(0.0, FREE_FLOW_SPEED - speed) * DT
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


def register_prediction(start, decision, follower_count, profiles):
    """Queue the chosen 10-second profile for an observed-vs-predicted check."""
    if not AUDIT:
        return
    PENDING.append({"start": float(start), "end": round(float(start) + 10.0, 3),
                    "decision": decision, "follower_count": follower_count,
                    "profiles": profiles, "samples": 0, "absolute_error": 0.0,
                    "squared_error": 0.0, "actual_distance_m": 0.0,
                    "predicted_distance_m": 0.0})
    COUNTS["prediction_windows"] += 1


def _finish_prediction(event):
    if not event["samples"]:
        COUNTS["prediction_windows_without_samples"] += 1
        return
    bucket = PREDICTION["all"]
    decision_bucket = PREDICTION[event["decision"]]
    for target in (bucket, decision_bucket):
        target["windows"] += 1
        target["samples"] += event["samples"]
        target["absolute_error"] += event["absolute_error"]
        target["squared_error"] += event["squared_error"]
        target["distance_error_m"] += abs(event["actual_distance_m"] - event["predicted_distance_m"])
        target["followers"] += event["follower_count"]


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
    groups = {}
    for name, data in GROUPS.items():
        groups[name] = {**data,
                        "mean_speed_mps": data["speed_sum"] / data["samples"] if data["samples"] else None}
    by_group = defaultdict(list)
    following_by_group = defaultdict(list)
    for data in VEHICLES.values():
        by_group[data["group"]].append(data["free_flow_shortfall_m"])
    for data in FOLLOWING_VEHICLES.values():
        following_by_group[data["group"]].append(data["free_flow_shortfall_m"])
    result = {"thresholds": {"hard_brake_mps2": HARD_BRAKE, "stop_speed_mps": STOP_SPEED,
                               "free_flow_speed_mps": FREE_FLOW_SPEED},
              "counts": dict(COUNTS), "groups": groups,
              "vehicle_free_flow_shortfall_m": {name: _distribution(values) for name, values in by_group.items()},
              "vehicle_free_flow_shortfall_samples_m": dict(by_group),
              "following_vehicle_free_flow_shortfall_m": {name: _distribution(values) for name, values in following_by_group.items()},
              "following_vehicle_free_flow_shortfall_samples_m": dict(following_by_group),
              "prediction_accuracy": {name: _normalise_prediction(data) for name, data in PREDICTION.items()},
              "prediction_accuracy_raw": {name: dict(data) for name, data in PREDICTION.items()}}
    with open(AUDIT, "w") as stream:
        json.dump(result, stream, indent=2)


atexit.register(_write_audit)

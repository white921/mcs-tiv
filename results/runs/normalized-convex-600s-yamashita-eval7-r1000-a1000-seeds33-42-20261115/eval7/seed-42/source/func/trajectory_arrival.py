"""Shared conflict-region and trajectory-arrival helpers.

The negotiation trigger already proves that the request and receiver safety
regions overlap within the transmitted prediction horizon. Yamashita TIV and
the proposal therefore share one region that contains both vehicle positions
at the detected overlap time and measure the first entry of each trajectory
into that region. A missing entry is an inconsistent negotiation event, not an
infinite arrival time.
"""
from __future__ import annotations

import math


HORIZON_S = 10.0
POSITION_EPSILON_M = 1e-6
TIME_EPSILON_S = 1e-6


def _available_indices(path, now, horizon_s=HORIZON_S):
    available = min(len(path.t), len(path.x), len(path.y))
    return [
        index for index, moment in enumerate(path.t[:available])
        if now - TIME_EPSILON_S <= float(moment)
        <= now + horizon_s + TIME_EPSILON_S
    ]


def _nearest_index(path, moment):
    available = min(len(path.t), len(path.x), len(path.y))
    if available == 0:
        raise ValueError("trajectory has no position samples")
    return min(
        range(available),
        key=lambda index: abs(float(path.t[index]) - moment),
    )


def _motion(path, index):
    """Return a finite local velocity vector at one trajectory sample."""
    available = min(len(path.t), len(path.x), len(path.y))
    pairs = []
    if index > 0:
        pairs.append((index - 1, index))
    if index + 1 < available:
        pairs.append((index, index + 1))
    for left, right in pairs:
        duration = float(path.t[right]) - float(path.t[left])
        if duration <= 0:
            continue
        dx = (float(path.x[right]) - float(path.x[left])) / duration
        dy = (float(path.y[right]) - float(path.y[left])) / duration
        if math.isfinite(dx) and math.isfinite(dy) and math.hypot(dx, dy) > 1e-9:
            return dx, dy
    return 0.0, 0.0


def conflict_region(
    request_path,
    receiver_path,
    collision,
    now,
    *,
    vehicle_length_m=5.0,
    vehicle_width_m=1.8,
    headway_s=1.5,
):
    """Build the shared region certified by one trajectory-conflict event.

    ``collision`` is the first conflict reported by ``checkPathCollision``.
    Its point is on the receiver trajectory, while a safety-region overlap
    does not require the request vehicle centre to reach that same point.  The
    shared region is therefore centred between the two vehicle positions at
    the detected event and expanded along the receiver heading until both
    positions are inside.  The plain dictionary can be transmitted in an MCM
    and logged as JSON.
    """
    try:
        center_x = float(collision["collide_x"])
        center_y = float(collision["collide_y"])
        detected_delay_s = float(collision["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("collision point and duration are required") from error
    values = (
        center_x,
        center_y,
        detected_delay_s,
        float(vehicle_length_m),
        float(vehicle_width_m),
        float(headway_s),
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("conflict-region values must be finite")
    if not 0 <= detected_delay_s <= HORIZON_S + TIME_EPSILON_S:
        raise ValueError("detected conflict lies outside the prediction horizon")
    if min(vehicle_length_m, vehicle_width_m) <= 0 or headway_s < 0:
        raise ValueError("vehicle dimensions must be positive and headway non-negative")

    event_time = float(now) + detected_delay_s
    request_index = _nearest_index(request_path, event_time)
    receiver_index = _nearest_index(receiver_path, event_time)
    request_dx, request_dy = _motion(request_path, request_index)
    receiver_dx, receiver_dy = _motion(receiver_path, receiver_index)
    receiver_speed = math.hypot(receiver_dx, receiver_dy)
    request_speed = math.hypot(request_dx, request_dy)

    heading_dx, heading_dy = receiver_dx, receiver_dy
    if math.hypot(heading_dx, heading_dy) <= 1e-9:
        heading_dx, heading_dy = request_dx, request_dy
    if math.hypot(heading_dx, heading_dy) <= 1e-9:
        heading_dx, heading_dy = 1.0, 0.0
    heading_rad = math.atan2(heading_dy, heading_dx)

    request_x = float(request_path.x[request_index])
    request_y = float(request_path.y[request_index])
    receiver_x = float(receiver_path.x[receiver_index])
    receiver_y = float(receiver_path.y[receiver_index])
    center_x = (request_x + receiver_x) / 2.0
    center_y = (request_y + receiver_y) / 2.0
    cosine, sine = math.cos(heading_rad), math.sin(heading_rad)
    half_dx = (request_x - receiver_x) / 2.0
    half_dy = (request_y - receiver_y) / 2.0
    event_longitudinal_separation = abs(half_dx * cosine + half_dy * sine)
    event_lateral_separation = abs(-half_dx * sine + half_dy * cosine)

    return {
        "schema_version": 1,
        "center_x_m": center_x,
        "center_y_m": center_y,
        "heading_rad": heading_rad,
        "longitudinal_radius_m": max(
            float(vehicle_length_m),
            max(request_speed, receiver_speed) * float(headway_s),
            event_longitudinal_separation,
        ),
        "lateral_radius_m": max(
            float(vehicle_width_m), event_lateral_separation),
        "detected_delay_s": detected_delay_s,
        "horizon_s": HORIZON_S,
    }


def arrival_delay(path, region, now):
    """Return first entry time into a shared detected conflict region.

    Negotiation cannot legitimately reach this function unless the trajectory
    enters ``region`` within its 10-second horizon, so absent entry signals
    inconsistent conflict metadata.
    """
    required = (
        "schema_version",
        "center_x_m",
        "center_y_m",
        "heading_rad",
        "longitudinal_radius_m",
        "lateral_radius_m",
        "horizon_s",
    )
    if not isinstance(region, dict) or any(name not in region for name in required):
        raise ValueError("shared conflict region is unavailable")
    if region["schema_version"] != 1:
        raise ValueError("unsupported conflict-region schema version")
    try:
        center_x = float(region["center_x_m"])
        center_y = float(region["center_y_m"])
        heading = float(region["heading_rad"])
        longitudinal_radius = float(region["longitudinal_radius_m"])
        lateral_radius = float(region["lateral_radius_m"])
        horizon_s = float(region["horizon_s"])
        now = float(now)
    except (TypeError, ValueError) as error:
        raise ValueError("conflict-region values must be numeric") from error
    values = (
        center_x,
        center_y,
        heading,
        longitudinal_radius,
        lateral_radius,
        horizon_s,
        now,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("conflict-region values must be finite")
    if min(longitudinal_radius, lateral_radius, horizon_s) <= 0:
        raise ValueError("conflict-region radii and horizon must be positive")
    if not math.isclose(horizon_s, HORIZON_S, abs_tol=TIME_EPSILON_S):
        raise ValueError("conflict-region horizon must equal 10 seconds")

    cosine, sine = math.cos(heading), math.sin(heading)
    for index in _available_indices(path, now, horizon_s):
        dx = float(path.x[index]) - center_x
        dy = float(path.y[index]) - center_y
        longitudinal = abs(dx * cosine + dy * sine)
        lateral = abs(-dx * sine + dy * cosine)
        if (longitudinal <= longitudinal_radius + POSITION_EPSILON_M
                and lateral <= lateral_radius + POSITION_EPSILON_M):
            return max(0.0, float(path.t[index]) - now)
    raise ValueError(
        "trajectory does not enter the detected conflict region within the horizon")

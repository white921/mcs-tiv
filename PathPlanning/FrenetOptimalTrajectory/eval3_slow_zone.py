"""Predictable speed restriction around the Eval.3 intersection.

The restriction represents a fixed road rule (for example, a raised crossing),
not an unexpected disturbance.  Candidate trajectories and the trajectory
followed by the live controller must therefore use the same speed profile.
This module re-parameterizes an already generated path along its original
geometry while respecting the vehicle's acceleration and deceleration limits.
"""
from __future__ import annotations

import bisect
import math
import os


ENVIRONMENT_SWITCH = "MCS_EVAL3_DOWNSTREAM_SLOW_ZONE"
ENVIRONMENT_LOCATION = "MCS_EVAL3_SLOW_ZONE_LOCATION"
ENVIRONMENT_START_OFFSET = "MCS_EVAL3_SLOW_ZONE_START_OFFSET_M"
ENVIRONMENT_LENGTH = "MCS_EVAL3_SLOW_ZONE_LENGTH_M"
ENVIRONMENT_SPEED_LIMIT = "MCS_EVAL3_SLOW_ZONE_SPEED_LIMIT_MPS"
RIGHT_EDGE_START_X_M = 157.2
LEFT_EDGE_END_X_M = 142.8

# The outgoing ``right`` edge starts at x=157.2 m.  The speed-hump section is
# deliberately short and begins 15 m downstream of the conflict area so the
# intersection-arrival term is unchanged.  Its length and 30 km/h limit allow
# even the lower-acceleration bus model on the LR through route to decelerate
# and recover within the 10 s prediction horizon when planning upstream.
DEFAULT_ZONE = {
    "case": "eval3",
    "location": "downstream",
    "edge_id": "right",
    "lane_id": "right_0",
    "start_offset_m": 15.0,
    "length_m": 2.0,
    "lane_center_y_m": -1.6,
    "lateral_tolerance_m": 1.0,
    "speed_limit_mps": 8.33,
    "reason": "fixed-predictable-speed-hump",
}


def zone_from_environment(environment=None):
    """Build one validated zone from the runner-controlled environment."""
    environment = os.environ if environment is None else environment
    zone = dict(DEFAULT_ZONE)
    location = environment.get(ENVIRONMENT_LOCATION, zone["location"])
    if location not in ("downstream", "upstream"):
        raise ValueError(
            f"{ENVIRONMENT_LOCATION} must be downstream or upstream")
    zone["location"] = location
    parameters = (
        (ENVIRONMENT_START_OFFSET, "start_offset_m", True),
        (ENVIRONMENT_LENGTH, "length_m", False),
        (ENVIRONMENT_SPEED_LIMIT, "speed_limit_mps", False),
    )
    for variable, field, allow_zero in parameters:
        if variable not in environment:
            continue
        value = float(environment[variable])
        if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
            qualifier = "non-negative" if allow_zero else "positive"
            raise ValueError(f"{variable} must be a finite {qualifier} number")
        zone[field] = value
    if location == "downstream":
        zone["edge_id"] = "right"
        zone["lane_id"] = "right_0"
        zone["start_x_m"] = RIGHT_EDGE_START_X_M + zone["start_offset_m"]
        zone["end_x_m"] = zone["start_x_m"] + zone["length_m"]
    else:
        zone["edge_id"] = "left"
        zone["lane_id"] = "left_0"
        zone["end_x_m"] = LEFT_EDGE_END_X_M - zone["start_offset_m"]
        zone["start_x_m"] = zone["end_x_m"] - zone["length_m"]
    return zone


ZONE = zone_from_environment()


def enabled_from_environment(environment=None):
    """Return whether the scenario switch is enabled, rejecting ambiguity."""
    environment = os.environ if environment is None else environment
    value = environment.get(ENVIRONMENT_SWITCH, "0")
    if value not in ("0", "1"):
        raise ValueError(f"{ENVIRONMENT_SWITCH} must be 0 or 1")
    return value == "1"


def manifest():
    """Return a serializable description of the fixed scenario condition."""
    return dict(ZONE)


def _cumulative_distances(xs, ys):
    distances = [0.0]
    for x0, y0, x1, y1 in zip(xs, ys, xs[1:], ys[1:]):
        distances.append(distances[-1] + math.hypot(x1 - x0, y1 - y0))
    return distances


def _interpolate(distances, values, position):
    if position <= distances[0]:
        return float(values[0])
    if position >= distances[-1]:
        return float(values[-1])
    right = bisect.bisect_right(distances, position)
    left = right - 1
    span = distances[right] - distances[left]
    if span <= 1e-12:
        return float(values[right])
    fraction = (position - distances[left]) / span
    return float(values[left]) + fraction * (
        float(values[right]) - float(values[left]))


def _zone_arc_bounds(xs, ys, distances):
    """Locate the fixed section on a path travelling along the right edge."""
    eligible = [
        index for index, (x, y) in enumerate(zip(xs, ys))
        if (ZONE["start_x_m"] - 0.2 <= x <= ZONE["end_x_m"] + 0.2 and
            abs(y - ZONE["lane_center_y_m"]) <= ZONE["lateral_tolerance_m"])
    ]
    if not eligible:
        return None

    first = eligible[0]
    last = eligible[-1]
    if xs[last] + 0.2 < ZONE["start_x_m"]:
        return None

    def boundary_arc(boundary_x, fallback_index):
        for index in range(1, len(xs)):
            if (abs(ys[index - 1] - ZONE["lane_center_y_m"]) >
                    ZONE["lateral_tolerance_m"] and
                    abs(ys[index] - ZONE["lane_center_y_m"]) >
                    ZONE["lateral_tolerance_m"]):
                continue
            x0, x1 = xs[index - 1], xs[index]
            if min(x0, x1) <= boundary_x <= max(x0, x1) and x1 != x0:
                fraction = (boundary_x - x0) / (x1 - x0)
                return distances[index - 1] + fraction * (
                    distances[index] - distances[index - 1])
        return distances[fallback_index]

    start = (0.0 if xs[0] >= ZONE["start_x_m"] else
             boundary_arc(ZONE["start_x_m"], first))
    end = boundary_arc(ZONE["end_x_m"], last)
    if end <= start:
        end = distances[last]
    return start, end


def _recompute_geometry(path):
    path.yaw = []
    path.ds = []
    path.c = []
    for x0, y0, x1, y1 in zip(path.x, path.y, path.x[1:], path.y[1:]):
        dx, dy = x1 - x0, y1 - y0
        path.yaw.append(math.atan2(dy, dx))
        path.ds.append(max(math.hypot(dx, dy), 0.0001))
    if path.yaw:
        path.yaw.append(path.yaw[-1])
        path.ds.append(path.ds[-1])
    else:
        path.yaw = [0.0]
        path.ds = [0.0001]
    for index in range(len(path.yaw) - 1):
        path.c.append((path.yaw[index + 1] - path.yaw[index]) / path.ds[index])
    path.c.append(path.c[-1] if path.c else 0.0)


def apply_to_path(path, *, max_speed, max_accel, max_decel, time_step=0.1):
    """Apply the speed restriction to one path in-place and return it.

    Position, speed, acceleration, and geometry arrays are updated together so
    proposal evaluation and live path following observe one coherent motion.
    """
    sample_count = len(path.t)
    if sample_count < 2 or len(path.x) != sample_count or len(path.y) != sample_count:
        return path
    if len(path.s_d) != sample_count:
        raise ValueError("slow-zone path needs one speed sample per time sample")

    original_speeds = [
        max(0.0, min(float(speed), float(max_speed)))
        for speed in path.s_d
    ]
    # Keep the normal-road profile aligned with the path so each negotiation
    # can later audit whether the fixed restriction was reached and whether
    # its temporary speed loss had recovered at the 10-second horizon.
    path.slow_zone_reference_s_d = list(original_speeds)
    path.slow_zone_context = {**manifest(), "enabled": True}

    original_x = list(path.x)
    original_y = list(path.y)
    distances = _cumulative_distances(original_x, original_y)
    bounds = _zone_arc_bounds(original_x, original_y, distances)
    if bounds is None or distances[-1] <= 0:
        return path
    zone_start, zone_end = bounds

    deceleration = abs(float(max_decel))
    if max_speed <= 0 or max_accel <= 0 or deceleration <= 0:
        raise ValueError("vehicle motion limits must be positive")

    progress = [0.0]
    speeds = [original_speeds[0]]
    for index in range(1, sample_count):
        current_position = progress[-1]
        current_speed = speeds[-1]
        if current_position < zone_start:
            distance_to_zone = zone_start - current_position
            # Reserve one control step for crossing the boundary.  Without
            # this discrete look-ahead, the continuous braking envelope can
            # enter the restricted section one sample above its limit.
            braking_distance = max(
                distance_to_zone - current_speed * time_step, 0.0)
            zone_envelope = min(
                float(max_speed),
                math.sqrt(ZONE["speed_limit_mps"] ** 2 +
                          2 * deceleration * braking_distance),
            )
        elif current_position <= zone_end:
            zone_envelope = ZONE["speed_limit_mps"]
        else:
            zone_envelope = float(max_speed)

        # The speed hump is an additional road constraint, not a replacement
        # for the trajectory mode.  Preserve a free/follow/yield/stop plan
        # whenever it is already slower than the restriction's envelope.
        target_speed = min(original_speeds[index], zone_envelope)

        next_speed = min(current_speed + float(max_accel) * time_step, target_speed)
        next_speed = max(next_speed, current_speed - deceleration * time_step, 0.0)
        next_position = min(
            distances[-1],
            current_position + (current_speed + next_speed) * time_step / 2,
        )
        progress.append(next_position)
        speeds.append(next_speed)

    # Avoid numerical re-parameterization when the original trajectory already
    # obeys the new restriction.  This makes the disabled and non-binding cases
    # exactly identical to the established simulation behavior.
    if all(abs(actual - original) <= 1e-12
           for actual, original in zip(speeds, original_speeds)):
        return path

    for name in ("x", "y", "s", "d", "d_d", "d_dd", "d_ddd"):
        values = getattr(path, name, None)
        if values is not None and len(values) == sample_count:
            setattr(path, name, [
                _interpolate(distances, values, position) for position in progress
            ])

    path.s_d = speeds
    path.s_dd = [0.0]
    path.s_dd.extend([
        (speeds[index] - speeds[index - 1]) / time_step
        for index in range(1, sample_count)
    ])
    path.s_ddd = [0.0]
    path.s_ddd.extend([
        (path.s_dd[index] - path.s_dd[index - 1]) / time_step
        for index in range(1, sample_count)
    ])
    _recompute_geometry(path)
    return path


def apply_to_paths(paths, *, max_speed, max_accel, max_decel, enabled=None):
    """Apply the scenario consistently to every candidate path."""
    if enabled is None:
        enabled = enabled_from_environment()
    if not enabled:
        return paths
    for path in paths:
        apply_to_path(
            path,
            max_speed=max_speed,
            max_accel=max_accel,
            max_decel=max_decel,
        )
    return paths

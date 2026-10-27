"""Pure, unit-safe loss calculations for deceleration-propagation studies.

The functions in this module deliberately do not know about TraCI.  Keeping
them pure prevents an evaluation of a counterfactual from changing a live
simulation and makes the 0.1-second integration convention testable.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class SpeedProfile:
    """Absolute-time speed samples for one vehicle."""

    vehicle_id: str
    times: tuple[float, ...]
    speeds: tuple[float, ...]

    def __post_init__(self):
        if len(self.times) != len(self.speeds) or len(self.times) < 2:
            raise ValueError("a profile needs matching time and speed samples")
        if any(right <= left for left, right in zip(self.times, self.times[1:])):
            raise ValueError("profile times must be strictly increasing")


def distance_loss(reference: SpeedProfile, case: SpeedProfile, *,
                  time_half_life_s: float | None = None) -> float:
    """Integrate ``reference speed - case speed`` over matching intervals.

    The result is a signed distance in metres.  Negative values are retained:
    they expose a faster case or an incorrectly constructed reference rather
    than being silently hidden by clipping.
    """
    if reference.vehicle_id != case.vehicle_id:
        raise ValueError("cannot compare profiles for different vehicles")
    if reference.times != case.times:
        raise ValueError("comparison profiles must use the same time grid")
    if time_half_life_s is not None and time_half_life_s <= 0:
        raise ValueError("time half-life must be positive")
    start = reference.times[0]
    total = 0.0
    for index in range(len(reference.times) - 1):
        left, right = reference.times[index:index + 2]
        elapsed = (left + right) / 2 - start
        weight = (1.0 if time_half_life_s is None else
                  2 ** (-elapsed / time_half_life_s))
        total += (
            (reference.speeds[index] - case.speeds[index])
            + (reference.speeds[index + 1] - case.speeds[index + 1])
        ) * (right - left) * weight / 2
    return total


def total_loss(reference: Mapping[str, SpeedProfile],
               case: Mapping[str, SpeedProfile], *,
               time_half_life_s: float | None = None) -> float:
    """Sum signed distance losses over the same explicitly selected vehicles."""
    if set(reference) != set(case):
        raise ValueError("reference and case must cover identical vehicle IDs")
    return sum(distance_loss(
        reference[vehicle_id], case[vehicle_id],
        time_half_life_s=time_half_life_s)
               for vehicle_id in sorted(reference))


def decision_margin(reference: Mapping[str, SpeedProfile],
                    accept: Mapping[str, SpeedProfile],
                    reject: Mapping[str, SpeedProfile], *,
                    time_half_life_s: float | None = None) -> dict:
    """Return losses and the documented ``L_reject - L_accept`` margin."""
    accept_loss = total_loss(
        reference, accept, time_half_life_s=time_half_life_s)
    reject_loss = total_loss(
        reference, reject, time_half_life_s=time_half_life_s)
    return {"accept_loss_m": accept_loss, "reject_loss_m": reject_loss,
            "reject_minus_accept_m": reject_loss - accept_loss}


def distance_losses(reference: Mapping[str, SpeedProfile],
                    case: Mapping[str, SpeedProfile], *,
                    time_half_life_s: float | None = None) -> dict[str, float]:
    """Return each vehicle's signed distance loss in metres."""
    if set(reference) != set(case):
        raise ValueError("reference and case must cover identical vehicle IDs")
    return {
        vehicle_id: distance_loss(
            reference[vehicle_id], case[vehicle_id],
            time_half_life_s=time_half_life_s)
        for vehicle_id in sorted(reference)
    }


def time_equivalent_decision(
    reference: Mapping[str, SpeedProfile],
    accept: Mapping[str, SpeedProfile],
    reject: Mapping[str, SpeedProfile],
    allowed_speeds: Mapping[str, float], *,
    request_arrival_s: float,
    receiver_arrival_s: float,
    loss_lambda: float = 1.0,
    time_half_life_s: float | None = None,
) -> dict:
    """Compare Accept and Reject on one time-equivalent scale.

    ``M = (t_request - t_receiver) + lambda *
    (loss_accept_seconds - loss_reject_seconds)``.  ``M <= 0`` accepts.
    Distance losses are converted with each vehicle's positive finite allowed
    speed, never its instantaneous speed.
    """
    if not math.isfinite(loss_lambda) or loss_lambda < 0:
        raise ValueError("loss lambda must be finite and non-negative")
    vehicle_ids = set(reference)
    if vehicle_ids != set(accept) or vehicle_ids != set(reject):
        raise ValueError("reference, accept and reject must cover identical vehicle IDs")
    if vehicle_ids != set(allowed_speeds):
        raise ValueError("allowed speeds must cover identical vehicle IDs")

    accept_by_vehicle = distance_losses(
        reference, accept, time_half_life_s=time_half_life_s)
    reject_by_vehicle = distance_losses(
        reference, reject, time_half_life_s=time_half_life_s)
    details = {}
    accept_loss_s = 0.0
    reject_loss_s = 0.0
    for vehicle_id in sorted(vehicle_ids):
        speed = float(allowed_speeds[vehicle_id])
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError(
                f"allowed speed must be positive and finite for vehicle {vehicle_id}")
        accept_seconds = accept_by_vehicle[vehicle_id] / speed
        reject_seconds = reject_by_vehicle[vehicle_id] / speed
        accept_loss_s += accept_seconds
        reject_loss_s += reject_seconds
        details[vehicle_id] = {
            "allowed_speed_mps": speed,
            "accept_loss_m": accept_by_vehicle[vehicle_id],
            "reject_loss_m": reject_by_vehicle[vehicle_id],
            "accept_loss_s": accept_seconds,
            "reject_loss_s": reject_seconds,
        }

    distance = decision_margin(
        reference, accept, reject, time_half_life_s=time_half_life_s)
    request_arrival_s = float(request_arrival_s)
    receiver_arrival_s = float(receiver_arrival_s)
    loss_margin_s = accept_loss_s - reject_loss_s
    weighted_loss_margin_s = loss_lambda * loss_margin_s
    if math.isinf(request_arrival_s) and request_arrival_s > 0:
        arrival_margin_s = math.inf
        final_margin_s = math.inf
        decision = "reject"
    elif math.isinf(receiver_arrival_s) and receiver_arrival_s > 0:
        arrival_margin_s = -math.inf
        final_margin_s = -math.inf
        decision = "accept"
    elif not (math.isfinite(request_arrival_s) and
              math.isfinite(receiver_arrival_s)):
        raise ValueError("arrival delays must be finite or positive infinity")
    else:
        arrival_margin_s = request_arrival_s - receiver_arrival_s
        final_margin_s = arrival_margin_s + weighted_loss_margin_s
        decision = "accept" if final_margin_s <= 0 else "reject"
    return {
        **distance,
        "request_arrival_s": request_arrival_s,
        "receiver_arrival_s": receiver_arrival_s,
        "arrival_margin_s": arrival_margin_s,
        "accept_time_equivalent_loss_s": accept_loss_s,
        "reject_time_equivalent_loss_s": reject_loss_s,
        "loss_margin_s": loss_margin_s,
        "loss_lambda": loss_lambda,
        "weighted_loss_margin_s": weighted_loss_margin_s,
        "final_margin_s": final_margin_s,
        "vehicle_loss_details": details,
        "decision": decision,
    }

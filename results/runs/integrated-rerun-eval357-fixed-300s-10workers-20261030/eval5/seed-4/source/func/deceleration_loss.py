"""Pure, unit-safe loss calculations for deceleration-propagation studies.

The functions in this module deliberately do not know about TraCI.  Keeping
them pure prevents an evaluation of a counterfactual from changing a live
simulation and makes the 0.1-second integration convention testable.
"""
from __future__ import annotations

from dataclasses import dataclass
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


def distance_loss(reference: SpeedProfile, case: SpeedProfile) -> float:
    """Integrate ``reference speed - case speed`` over matching intervals.

    The result is a signed distance in metres.  Negative values are retained:
    they expose a faster case or an incorrectly constructed reference rather
    than being silently hidden by clipping.
    """
    if reference.vehicle_id != case.vehicle_id:
        raise ValueError("cannot compare profiles for different vehicles")
    if reference.times != case.times:
        raise ValueError("comparison profiles must use the same time grid")
    return sum(
        ((reference.speeds[index] - case.speeds[index])
         + (reference.speeds[index + 1] - case.speeds[index + 1]))
        * (reference.times[index + 1] - reference.times[index]) / 2
        for index in range(len(reference.times) - 1)
    )


def total_loss(reference: Mapping[str, SpeedProfile],
               case: Mapping[str, SpeedProfile]) -> float:
    """Sum signed distance losses over the same explicitly selected vehicles."""
    if set(reference) != set(case):
        raise ValueError("reference and case must cover identical vehicle IDs")
    return sum(distance_loss(reference[vehicle_id], case[vehicle_id])
               for vehicle_id in sorted(reference))


def decision_margin(reference: Mapping[str, SpeedProfile],
                    accept: Mapping[str, SpeedProfile],
                    reject: Mapping[str, SpeedProfile]) -> dict:
    """Return losses and the documented ``L_reject - L_accept`` margin."""
    accept_loss = total_loss(reference, accept)
    reject_loss = total_loss(reference, reject)
    return {"accept_loss_m": accept_loss, "reject_loss_m": reject_loss,
            "reject_minus_accept_m": reject_loss - accept_loss}

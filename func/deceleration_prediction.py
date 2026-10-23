"""Read-only shadow prediction for the deceleration-propagation proposal.

This first implementation intentionally evaluates the two negotiating cars
only.  It records when follower propagation cannot yet be constructed from
the information carried by MCM trajectories, instead of inventing follower
motions or making an active decision.  The adapter boundary is kept explicit
for the next stage, where copied CAV state can reuse the live planner.
"""
from __future__ import annotations

import atexit
import json
import os
from collections import Counter

from deceleration_loss import SpeedProfile, decision_margin

COUNTS = Counter()
RECORDS = []
MODE = os.environ.get("MCS_DECELERATION_MODE", "off")
if MODE not in ("off", "shadow"):
    raise ValueError("MCS_DECELERATION_MODE must be off or shadow")


def configure(mode):
    """Select a mode explicitly; active control is intentionally unavailable."""
    global MODE
    if mode not in ("off", "shadow"):
        raise ValueError("MCS_DECELERATION_MODE must be off or shadow")
    MODE = mode


def _profile(path, vehicle_id, now, horizon=10.0):
    """Read a common 10 s grid from an existing planned/desired path.

    No extrapolation is invented.  A shorter trajectory is reported as an
    unsupported shadow evaluation, which is safer than treating its tail as
    zero speed.
    """
    pairs = [(float(time), float(speed)) for time, speed in zip(path.t, path.s_d)
             if now - 1e-6 <= time <= now + horizon + 1e-6]
    if len(pairs) < 2 or pairs[-1][0] < now + horizon - 1e-6:
        raise ValueError("trajectory does not cover the full prediction horizon")
    return SpeedProfile(str(vehicle_id), tuple(time for time, _ in pairs),
                        tuple(speed for _, speed in pairs))


def record_shadow(receiver, desired, alternative, now):
    """Compare accept/reject direct-car trajectories without mutating state.

    Reference trajectories are the pre-negotiation planned paths.  The common
    reference cancels in the decision margin, but is retained in the record so
    individual signed losses remain auditable.  Follower propagation is not
    claimed here: current MCM objects lack mutable CAV state required to run
    the existing planner for each follower.
    """
    if MODE != "shadow":
        return None
    COUNTS["shadow_attempts"] += 1
    try:
        sender_id = str(desired.vehID)
        receiver_id = str(receiver.id)
        # Match the live TIV logic: a receiver can hold several packets from
        # one sender, and the newest planned trajectory is the relevant
        # counterfactual baseline.
        sender_planned = max(
            (path for path in receiver.receivedPaths
             if path.vehID == desired.vehID and path.type == "planned"),
            key=lambda path: path.t[0])
        reference = {
            sender_id: _profile(sender_planned, sender_id, now),
            receiver_id: _profile(receiver.plannedPath, receiver_id, now),
        }
        accept = {
            sender_id: _profile(desired, sender_id, now),
            receiver_id: _profile(alternative, receiver_id, now),
        }
        reject = dict(reference)
        result = decision_margin(reference, accept, reject)
    except (StopIteration, AttributeError, TypeError, ValueError) as error:
        COUNTS["shadow_unsupported"] += 1
        record = {"time": now, "receiver": str(receiver.id),
                  "sender": str(getattr(desired, "vehID", "unknown")),
                  "status": "unsupported", "reason": str(error)}
    else:
        COUNTS["shadow_evaluations"] += 1
        record = {"time": now, "receiver": receiver_id, "sender": sender_id,
                  "desired_path_id": desired.pathID,
                  "receiver_planned_path_id": receiver.plannedPath.pathID,
                  "alternative_path_id": alternative.pathID,
                  "status": "direct-cars-only",
                  "followers": "not-yet-modelled",
                  **result}
    if len(RECORDS) < 500:
        RECORDS.append(record)
    return record


def _write_audit():
    destination = os.environ.get("MCS_DECELERATION_AUDIT")
    if destination:
        with open(destination, "w") as stream:
            json.dump({"mode": MODE, "counts": dict(COUNTS), "records": RECORDS},
                      stream, indent=2)


atexit.register(_write_audit)

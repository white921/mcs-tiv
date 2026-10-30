"""Paired SUMO/MCS checkpoints for exact mid-run continuation.

FCD and JSONL traces are replay artifacts; they do not contain the planner,
agreement, random-generator, or metric-accumulator state needed to continue a
run.  A checkpoint therefore stores SUMO's native state and a trusted local
pickle of the MCS state at the same simulation timestamp.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import pickle
import platform
import shutil


SCHEMA_VERSION = 1


def configured_interval():
    value = float(os.environ.get("MCS_CHECKPOINT_INTERVAL", "0"))
    if value < 0:
        raise ValueError("MCS_CHECKPOINT_INTERVAL must be non-negative")
    return value


def configured_times():
    """Return explicit one-shot checkpoint times from the environment."""
    raw = os.environ.get("MCS_CHECKPOINT_AT", "").strip()
    if not raw:
        return ()
    values = tuple(float(item.strip()) for item in raw.split(",") if item.strip())
    if any(value <= 0 for value in values):
        raise ValueError("MCS_CHECKPOINT_AT times must be positive")
    return values


def is_due(sim_time, interval=None):
    interval = configured_interval() if interval is None else float(interval)
    if interval <= 0 or sim_time <= 0:
        return False
    return abs(sim_time / interval - round(sim_time / interval)) <= 1e-6


def is_requested(sim_time, times=None):
    """Whether ``sim_time`` matches an explicit one-shot checkpoint time."""
    times = configured_times() if times is None else tuple(float(value) for value in times)
    return any(abs(float(sim_time) - value) <= 1e-6 for value in times)


def checkpoint_name(sim_time):
    return f"t{sim_time:09.1f}"


def save(traci, root, sim_time, payload, metadata=None):
    """Atomically save synchronized SUMO and Python controller state."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    name = checkpoint_name(sim_time)
    destination = root / name
    temporary = root / ("." + name + ".tmp")
    if destination.exists():
        raise FileExistsError(f"checkpoint already exists: {destination}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    sumo_state = temporary / "sumo-state.xml.gz"
    traci.simulation.saveState(str(sumo_state))
    with (temporary / "mcs-state.pkl").open("wb") as stream:
        pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "simulation_time_s": float(sim_time),
        "sumo_state": sumo_state.name,
        "mcs_state": "mcs-state.pkl",
        "python_version": platform.python_version(),
        **(metadata or {}),
    }
    (temporary / "checkpoint.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary.rename(destination)
    return destination


def load(directory):
    """Load a trusted local MCS checkpoint and validate its paired files."""
    directory = Path(directory).resolve()
    manifest_path = directory / "checkpoint.json"
    if not manifest_path.is_file():
        raise ValueError(f"checkpoint manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported checkpoint schema")
    sumo_state = directory / manifest["sumo_state"]
    mcs_state = directory / manifest["mcs_state"]
    if not sumo_state.is_file() or not mcs_state.is_file():
        raise ValueError("checkpoint pair is incomplete")
    with mcs_state.open("rb") as stream:
        payload = pickle.load(stream)
    return manifest, payload, sumo_state


def capture_shared_modules(evaluation_metrics, deceleration_prediction, thesis_tiv):
    """Capture mutable cross-scenario audit and decision state."""
    return {
        "evaluation_metrics": {
            "COUNTS": evaluation_metrics.COUNTS,
            "GROUPS": evaluation_metrics.GROUPS,
            "VEHICLES": evaluation_metrics.VEHICLES,
            "FOLLOWING_VEHICLES": evaluation_metrics.FOLLOWING_VEHICLES,
            "PENDING": evaluation_metrics.PENDING,
            "PREDICTION": evaluation_metrics.PREDICTION,
            "PREDICTION_EVENTS": evaluation_metrics.PREDICTION_EVENTS,
            "PHYSICAL_COLLISION_FRAMES": evaluation_metrics.PHYSICAL_COLLISION_FRAMES,
            "ACTIVE_PHYSICAL_COLLISIONS": evaluation_metrics.ACTIVE_PHYSICAL_COLLISIONS,
        },
        "deceleration_prediction": {
            "COUNTS": deceleration_prediction.COUNTS,
            "RECORDS": deceleration_prediction.RECORDS,
            "ACTIVE_DECISION_UNTIL": deceleration_prediction.ACTIVE_DECISION_UNTIL,
            "MODE": deceleration_prediction.MODE,
        },
        "thesis_tiv": {
            "COUNTS": thesis_tiv.COUNTS,
            "EXAMPLES": thesis_tiv.EXAMPLES,
            "ORACLE_EVENT_COUNT": thesis_tiv.ORACLE_EVENT_COUNT,
        },
    }


def _replace_mapping(target, value):
    target.clear()
    target.update(value)


def restore_shared_modules(
        state, evaluation_metrics, deceleration_prediction, thesis_tiv):
    metrics = state["evaluation_metrics"]
    for name in ("COUNTS", "GROUPS", "VEHICLES", "FOLLOWING_VEHICLES",
                 "PREDICTION"):
        _replace_mapping(getattr(evaluation_metrics, name), metrics[name])
    for name in ("PENDING", "PREDICTION_EVENTS"):
        getattr(evaluation_metrics, name)[:] = metrics[name]
    evaluation_metrics.PHYSICAL_COLLISION_FRAMES[:] = metrics.get(
        "PHYSICAL_COLLISION_FRAMES", [])
    evaluation_metrics.ACTIVE_PHYSICAL_COLLISIONS.clear()
    evaluation_metrics.ACTIVE_PHYSICAL_COLLISIONS.update(
        metrics.get("ACTIVE_PHYSICAL_COLLISIONS", set()))
    prediction = state["deceleration_prediction"]
    _replace_mapping(deceleration_prediction.COUNTS, prediction["COUNTS"])
    deceleration_prediction.RECORDS[:] = prediction["RECORDS"]
    _replace_mapping(
        deceleration_prediction.ACTIVE_DECISION_UNTIL,
        prediction["ACTIVE_DECISION_UNTIL"])
    deceleration_prediction.MODE = prediction["MODE"]
    tiv = state["thesis_tiv"]
    _replace_mapping(thesis_tiv.COUNTS, tiv["COUNTS"])
    thesis_tiv.EXAMPLES[:] = tiv["EXAMPLES"]
    thesis_tiv.ORACLE_EVENT_COUNT = tiv.get("ORACLE_EVENT_COUNT", 0)


def restore_vehicle_controls(traci, vehicles):
    """Restore TraCI client-side control modes and the pending speed command."""
    running_ids = set(traci.vehicle.getIDList())
    for vehicle in vehicles:
        if vehicle.id not in running_ids:
            continue
        traci.vehicle.setLaneChangeMode(vehicle.id, 0b000000000000)
        traci.vehicle.setSpeedMode(vehicle.id, 0b100000)
        if vehicle.plannedPath is not None:
            vehicle.executionDrive()

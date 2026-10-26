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


def is_due(sim_time, interval=None):
    interval = configured_interval() if interval is None else float(interval)
    if interval <= 0 or sim_time <= 0:
        return False
    return abs(sim_time / interval - round(sim_time / interval)) <= 1e-6


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

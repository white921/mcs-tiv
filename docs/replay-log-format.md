# MCS replay bundle

The replay bundle is the durable output contract between a simulation and
visualization or analysis tools.  It deliberately separates motion, MCS
decisions, and restart state.

## Bundle layout

```text
<run>/
├── manifest.json
├── vehicle-states.jsonl
├── negotiations.jsonl
├── conflicts.jsonl
├── prediction-events.jsonl
├── fcd.xml.gz
├── source/
│   └── ... scenario source and SUMO network ...
└── checkpoints/                 # reserved for restart support
    └── <simulation-time>/
        ├── checkpoint.json
        ├── sumo-state.xml.gz
        └── mcs-state.json.gz
```

`manifest.json` is the entry point and records the schema versions, program
versions, exact fixed-input hash, command, source hashes, and completion state.

## Motion log

`vehicle-states.jsonl` schema version 2 stores one frame per simulation step.
Each vehicle includes:

- identity and class: vehicle ID, SUMO type, car/bus group;
- pose and shape: x, y, angle, slope, length, width, height;
- motion: speed and acceleration;
- lane context: road, lane, longitudinal and lateral lane position;
- SUMO signals: original signal bitset and decoded blinkers, brake light,
  headlights, reversing light, doors, and other flags;
- MCS state: controller/junction status, current and desired path IDs, leader,
  wait state, and agreement IDs.

The raw SUMO signal integer remains in the log so future tools are not limited
to the first viewer's decoded fields.

## SUMO-compatible FCD

`fcd.xml.gz` records the native SUMO trajectory with acceleration and signal
bits enabled.  It is useful for SUMO tooling and independent trajectory
validation.  It is not the source of MCS negotiation semantics.

## Event logs

Negotiation, conflict, and prediction events remain append-only JSONL streams.
Every event has a simulation timestamp and stable participant/path IDs so a
viewer can join events to motion frames without embedding UI-specific data in
the simulation.

## Restart checkpoints

FCD is replay data, not restart state.  A scientifically valid branch from an
intermediate time needs both layers below at the same simulation time:

1. `sumo-state.xml.gz`: SUMO vehicle/network state, including SUMO RNG state.
2. `mcs-state.json.gz`: explicit, versioned serialization of MCS state:
   active vehicle controllers, planned/desired/received paths, pending and
   received agreements, central path-server buffers, input-schedule cursor,
   vehicle ID counters, experiment configuration, and Python RNG states.

`checkpoint.json` must bind both files with SHA-256 hashes, schema versions,
simulation time, source commit/hash, fixed-input hash, Python/SUMO versions,
and a compatibility declaration.  Pickling controller objects is intentionally
not the durable format because it ties old experiments to Python class layout.

Checkpoint writing and restore are a separate implementation milestone.  Until
both SUMO and MCS state are serialized and a replay-to-checkpoint equivalence
test passes, a run must restart from time zero.

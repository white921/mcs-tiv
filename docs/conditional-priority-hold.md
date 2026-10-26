# Conditional priority hold

This experiment keeps Yamashita-style pairwise negotiation, but separates an
agreement into two stages:

1. **Remembered**: preserve the accepted priority relation across one-second
   desired-trajectory ID refreshes. The key is the priority vehicle, yielding
   vehicle, and a 2 m physical conflict region—not a path ID.
2. **Active**: generate and apply the yielding trajectory only when the
   priority vehicle has a trajectory that advances toward the conflict,
   sufficient current/proven progress, and no close SUMO leader blocking it.

The hold is released instead of being applied when the conflict participants
or region change, another conflict appears, the yielding queue grows beyond
the configured limit, no safe alternative trajectory exists, the priority
vehicle makes no progress for the timeout, or the maximum duration expires.

The implementation is opt-in with `--conditional-priority-hold`. Existing
baseline and proposal runs are unchanged when the flag is absent. Lifecycle
events are written to `negotiations.jsonl` as
`priority_hold_remembered`, `priority_hold_pending`,
`priority_hold_activated`, `priority_hold_refreshed`, and
`priority_hold_released`.

## Standard run artifacts

`scripts/run_thesis_batch.py` now enables diagnostics by default. Every run
writes FCD (including acceleration and signal bits) and negotiation events.
Eval.3, Eval.5, and Eval.7 additionally write vehicle-state, conflict, and
runtime JSONL files for the replay viewer.

Eval.3, Eval.5, and Eval.7 also write paired checkpoints every 60 seconds by
default. Each checkpoint contains:

- SUMO native state with RNG and 16-digit precision;
- MCS controller instances, planned/desired/alternative trajectories, and
  agreement/priority-hold state;
- fixed-input cursor and Python random-generator states;
- online evaluation and prediction accumulators.

Resume one Eval.3, Eval.5, or Eval.7 task with `--resume-checkpoint PATH`.
Short continuation tests confirmed that all three cases produced identical
per-frame vehicle-state logs and the same aggregate speed after resuming from
the paired checkpoint. Eval.7 also reapplies the pending zero-speed command to
its stationary `stone` obstacle because that TraCI command is not serialized
in SUMO's native state file.

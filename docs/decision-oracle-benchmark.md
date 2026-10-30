# Accept/Reject decision oracle benchmark

## Scope and fixed choices

This is an offline, decision-level oracle.  It is not an online decision rule
and neither its label nor its loss contains TIV, R(X), a performance term, or
a policy threshold.  Each event starts immediately before a physically
feasible receiver decision and is continued for exactly 10.0 seconds at the
existing 0.1-second cadence.  Ties are fixed in advance as
`abs(D_accept - D_reject) <= 1e-6 s`.

For branch `b`, vehicle `i` contributes

`D_i(b) = sum_t 0.1 * max(0, 1 - v_i(t)/v_ref_i(t))`.

`v_ref_i(t)` is SUMO's current allowed speed, which incorporates road and
vehicle-type limits.  The cohort is the union of vehicle IDs present at the
checkpoint and the fixed-input entrants during the horizon in either branch.
Thus a vehicle only present in one branch is not silently omitted from the
comparison.  Raw free-flow lost distance, mean speed, stop time, hard-brake
time, arrivals and SUMO physical-collision frames are retained as secondary
metrics.

## Checkpoint contract

The persisted checkpoint is made at the end of the simulator step immediately
before the decision.  It consists of SUMO native state (including RNG), the
controller object graph, planned/desired/received trajectories, agreement
state, fixed-input queues/cursor, Python and vehicle-type RNG state, and
diagnostic/metric state.  Each branch deterministically replays the next 0.1 s
to the decision boundary.  Before applying a choice it hashes the decision
identity, time, every active vehicle's position and speed, the fixed-input
cursor, both RNG states, controller/agreement fields and the full path content.
The reject branch is aborted unless this fingerprint exactly matches the
accept branch.  This outer-step replay avoids trying to pickle a Python call
stack while still proving that only the target choice differs.

The accept branch applies the existing agreement/alternative-path mechanism
for the selected event; the reject branch applies the existing rejected-path
mechanism.  Every later decision is made by the same selected policy.  A
branch is invalid if restoration differs, a requested forced action is not
physically feasible, an agreement cannot complete, a collision occurs, or the
10-second run does not complete.

## Policy scoring

The audit evaluates both the Yamashita/TIV decision and the current proposal
decision from the identical pre-decision object graph.  For policy choice
`p`, `regret = D_p - min(D_accept, D_reject)` and a tie is correct for either
choice.  Predictor outputs and their realised errors are stored separately;
they do not change the oracle label.

## Corpus discipline

Events are selected in ascending `(simulation_time, receiver_id, sender_id,
desired_path_id)` order, deduplicated by that tuple, and capped at 20 valid
Eval.3 fixed-seed events.  One invocation owns one
`results/runs/<experiment-id>/` directory; each event owns its checkpoint,
accept/reject logs, metrics and manifest.  A corpus with any incomplete event
is not committed or pushed.

The single-event runner used for the first smoke test is:

```bash
python scripts/run_decision_oracle.py \
  --sumo-home /path/to/sumo \
  --python /path/to/python \
  --output results/runs/<unique-id> \
  --seed 1 --duration 300 \
  --event-ordinal 1 --event-time 27.4
```

It creates one event directory with the capture checkpoint, two branch logs,
boundary records, 0.1-second state traces, branch manifests, the oracle label,
and Yamashita/proposal correctness and regret.  A nonzero process exit, changed
source hash, missing boundary record, mismatched fingerprint, or collision
leaves the event invalid rather than silently substituting another run.

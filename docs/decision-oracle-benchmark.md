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

The checkpoint must be made after the candidate alternative is generated and
before the decision is applied.  It consists of SUMO native state (including
RNG), the controller object graph, planned/desired/received trajectories,
agreement state, fixed-input queues/cursor, Python and vehicle-type RNG state,
diagnostic/metric state, and a compact fingerprint of time, vehicle IDs,
positions, speeds, fixed-input cursor, RNG state and controller-state hash.
Both branches record the same restored fingerprint in their manifests.

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

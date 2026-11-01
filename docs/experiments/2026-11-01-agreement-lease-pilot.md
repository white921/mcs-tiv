# Acceptance-signal lease pilot

## Purpose

Test the smallest coordination change suggested by the Eval.7 300/1000
diagnosis.  A receiver may reuse a recent Accept for the same sender and the
same physical conflict region for one second.  The lease retains neither the
old alternative trajectory nor a priority/yield command.

This is an implementation/development experiment, not final evidence of the
proposal's superiority.

## Fixed design before results

- Source branch: `codex/agreement-lease-pilot`
- Scenario: Eval.7, requesting/accepting flows 300/1000 veh/h
- Seeds: 6 and 8
- Duration: 300 seconds
- Methods:
  - Yamashita TIVtep with a 1.0-second acceptance-signal lease
  - harm-only proposal with lambda 2 and the same 1.0-second lease
- Fixed inputs: the committed 300/1000 flow-sweep inputs already used by the
  no-lease comparison
- SUMO/Python target: SUMO 1.28.0 / Python 3.15.1 on `sgnlab`
- Physical conflict-region tolerance: 2.0 m
- Required agreement IDs: always taken from the refreshed desired path; new
  participants do not inherit another receiver's Accept
- Every refresh regenerates a feasible alternative trajectory before a lease
  may be reused

## Comparison target

The completed no-lease Eval.7 flow-ratio runs for the same 300/1000 inputs and
seeds.  Compare each method only against its own no-lease run first; then
compare Yamashita and proposal under the common lease procedure.

## Validation and metrics

Require `exit_code: 0`, `source_unchanged: true`, matching fixed-input prefix
hashes, required artifacts, no serious runner/SUMO error, and zero measured
physical collisions before using a run.

Report per seed and method:

- all-vehicle mean speed;
- stopped time and maximum stopped queue;
- hard braking and completed vehicles;
- negotiation decisions and `desired_path_disappeared` cancellations;
- acceptance leases created, reused, expired, and cleared;
- the previously diagnosed stopped vehicles and their time at the lane end.

## Decision rule and limitations

The pilot is promising only if cancellation/terminal stopping falls without a
material hard-braking or physical-collision regression in both diagnosed
seeds.  A favorable result does not establish general superiority.  It must be
followed by all five fixed seeds and then unused inputs.  A poor result is kept
and reported; lease duration or seeds are not changed after seeing this pilot.

## Result

Not run yet.

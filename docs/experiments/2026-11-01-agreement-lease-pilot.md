# Acceptance-signal lease pilot

## 状態

`completed`

The 1.0-second acceptance-signal lease was not adopted.

- Execution source: `codex/agreement-lease-pilot@f35424f1c78a13068a3cbd4f98b5f9d05c778d37`
- Result commit: the dedicated result commit containing this record
- Yamashita result: `results/runs/agreement-lease1-eval7-r300-a1000-yamashita-seeds6-8-300s-20261101T`
- Proposal result: `results/runs/agreement-lease1-eval7-r300-a1000-proposal-lambda2-seeds6-8-300s-20261101T`
- Comparison target: the completed no-lease 300/1000 runs recorded in
  `2026-11-01-eval7-flow-ratio-sweep.md`

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

All four runs completed normally.  Every run has `exit_code: 0`,
`source_unchanged: true`, source commit `f35424f`, a clean start, matching
300-second fixed-input prefix hashes, the required artifacts, and zero physical
collisions.  The manifests record a 1.0-second `accept-signal-only` lease with
`retains_priority_or_trajectory: false`.  Runner, stdout, stderr, and SUMO logs
contained no serious error.

After validation, the JSONL diagnostics were losslessly gzip-compressed for the
result commit.  `gzip -t` succeeded for every compressed file; the original
filenames are recovered by ordinary decompression.

### Proposal lambda 2 compared with its own no-lease run

| seed | lease reuse | speed, no lease -> lease [m/s] | stopped time [s] | hard-brake time [s] | completed vehicles | desired-path cancellations |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 65 | 9.2929 -> 9.2929 | 409.9 -> 409.9 | 1.6 -> 1.6 | 82 -> 82 | 172 -> 198 |
| 8 | 21 | 9.8104 -> 9.9548 | 71.2 -> 57.4 | 2.0 -> 0.6 | 93 -> 94 | 90 -> 89 |

Seed 8 improved by 0.1444 m/s, reduced stopped time by 13.8 seconds, and
completed one additional vehicle.  However, the two already diagnosed
lane-end stops did not change: vehicle 33 still stopped for 16.3 seconds and
vehicle 35 for 22.0 seconds on `main_0`.  Most of the stopped-time reduction
came from removing vehicle 67's 11.4-second stop, not from resolving the
diagnosed terminal-stopping mechanism.

Seed 6 did not improve any traffic metric.  Vehicle 73 still stopped at the
lane end for 117.0 seconds, the maximum stopped queue remained eight vehicles,
and 82 vehicles completed the network.  Despite 65 lease reuses and 39 fewer
decision events, desired-path cancellations increased by 26.  This is the
pilot's decisive failure against the pre-registered rule.

### Yamashita method compared with its own no-lease run

| seed | lease reuse | speed, no lease -> lease [m/s] | stopped time [s] | hard-brake time [s] | completed vehicles | desired-path cancellations |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 2 | 10.1654 -> 10.1654 | 7.5 -> 7.5 | 2.5 -> 2.5 | 91 -> 91 | 22 -> 22 |
| 8 | 9 | 10.2208 -> 10.2245 | 7.9 -> 12.5 | 4.9 -> 6.1 | 92 -> 92 | 35 -> 45 |

The lease left seed 6's traffic trajectory unchanged.  In seed 8 the speed
change was only +0.0037 m/s, while stopped time, hard braking, the maximum
stopped queue, and cancellations all worsened.  The coordination rule can
therefore introduce side effects even when it is applied to the comparison
method as well as the proposal.

### Common-lease method comparison

With the same 1.0-second lease, the two-seed mean speed was 10.1950 m/s for the
Yamashita method and 9.6239 m/s for proposal lambda 2.  The proposal remained
0.5711 m/s (5.6%) slower.  It lost by 0.8725 m/s in seed 6 and 0.2697 m/s in
seed 8.  All runs remained physically collision-free.

## Conclusion

The one-second acceptance-signal lease is not adopted.  It produced a useful
but seed-specific reduction in repeated decisions for seed 8, but did not fix
the terminal stopping in either diagnosed vehicle pair and had no traffic
benefit in the most severe seed 6.  In seed 6 it also increased cancellations,
showing that reusing an Accept signal alone does not preserve the complete set
of participants needed to finish a merge.

The failure narrows the next design question: the missing state is not merely
whether one receiver recently accepted.  A future change must address the
stability of the whole participant set or the merge's remaining feasibility,
while still refreshing trajectories and safety checks.  That is a larger
causal change and should be specified as a separate experiment rather than by
retuning this lease duration after seeing these results.

## Limitations

- This is a two-seed diagnostic on cases selected because they previously
  failed; it is not an estimate of general traffic performance.
- The lease duration and scope were fixed before results and were not tuned.
- Completed-vehicle counts exclude the fixed roadside obstacle and count a
  vehicle as completed only when it appeared in FCD and left before 300 seconds.
- Maximum stopped queue uses simultaneous vehicles below 0.1 m/s; lane-end
  stopping uses `main_0` positions at or beyond 295 m.

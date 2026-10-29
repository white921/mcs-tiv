# Eval.3 downstream speed-hump experiment

## Purpose

This experiment changes only the road condition shared by both decision
methods.  It adds a predictable speed hump to the `right` outgoing edge after
the Eval.3 conflict area.  The existing arrival-time term is therefore not
changed by keeping the restriction downstream of the intersection.

The hypothesis is that Yamashita TIV sees the recovered terminal speed, while
the proposal also evaluates the temporary speed loss and its propagation to
followers over the 10-second trajectory.

## Fixed scenario

- Case: Eval.3
- Edge/lane: `right` / `right_0`
- Start: 15 m after the outgoing edge begins
- Length: 2 m
- Limit: 8.33 m/s (30 km/h)
- Applies to: candidate trajectories and live path following
- Vehicle models: both cars and buses on the LR through route decelerate
  through the section and recover to the same terminal speed as the normal
  road by 10 seconds in the checked upstream planning state

The BR turn is already below 30 km/h at this location in the checked planning
state, so the added limit is non-binding for that trajectory.  The experiment's
deliberate temporary speed loss is created on the LR through traffic that
shares the downstream `right` corridor.

The restriction is disabled by default.  Add
`--eval3-downstream-slow-zone` to enable it.  Omitting that option preserves
the normal-road scenario.

## New paired runs

Run these two commands at the same time to use ten SUMO workers in total.  Do
not start them while another ten-process batch is active on the Ubuntu host.

Yamashita TIV, five workers:

```bash
"$SIM_PYTHON" scripts/run_thesis_batch.py \
  --sumo-home "$SUMO_ROOT" \
  --python "$SIM_PYTHON" \
  --run-name eval3-downstream-speed-hump-yamashita-fixed-300s-seeds1-5 \
  --cases eval3 \
  --seeds 1 2 3 4 5 \
  --workers 5 \
  --duration 300 \
  --bus-allocation fixed \
  --eval3-downstream-slow-zone \
  --diagnostic-traces \
  --checkpoint-interval 60
```

Proposal, lambda=1 without follower-count normalization, five workers:

```bash
"$SIM_PYTHON" scripts/run_thesis_batch.py \
  --sumo-home "$SUMO_ROOT" \
  --python "$SIM_PYTHON" \
  --run-name eval3-downstream-speed-hump-proposal-lambda1-fixed-300s-seeds1-5 \
  --cases eval3 \
  --seeds 1 2 3 4 5 \
  --workers 5 \
  --duration 300 \
  --bus-allocation fixed \
  --eval3-downstream-slow-zone \
  --deceleration-active \
  --deceleration-loss-lambda 1.0 \
  --diagnostic-traces \
  --checkpoint-interval 60
```

`SIM_PYTHON` must name the project Python used with SUMO 1.28, and `SUMO_ROOT`
must name that environment's SUMO package directory.

## Normal-road controls

Use the already completed 300-second fixed-input controls rather than running
the normal road again:

- Yamashita TIV: branch `codex/yamashita-baseline`, experiment
  `yamashita-axisfix-eval3-eval5-fixed-300s-seeds1-5-20261028T`
- Proposal lambda=1: experiment
  `proposal-lambda1-axis-fix-eval3-eval5-fixed-300s-seeds1-5-uniform10s-20261028T`

For Eval.3, both controls contain Seeds 1 through 5, use the same fixed-input
300-second prefixes, and report `exit_code: 0` and `source_unchanged: true` for
every run.

## Completion checks

For each new experiment, verify all of the following before using results:

1. The experiment manifest is `completed` with five completed and zero failed
   simulations.
2. Every run manifest records `exit_code: 0`, `source_unchanged: true`, the
   correct Seed, 300 seconds, and fixed input.
3. `eval3_downstream_slow_zone` records edge `right`, 15 m offset, 2 m length,
   and 8.33 m/s.
4. Only the proposal manifests contain `decision_method:
   deceleration-propagation`, `loss_lambda: 1.0`, and a deceleration audit.
5. Runner and per-run logs contain no exception, traceback, collision-process
   failure, or early termination.
6. Compare each method first against its own normal-road control, then compare
   the changes between methods.  Report all-speed, route/direction speeds,
   stopped time, throughput where available, hard braking, and physical
   collisions by Seed and as paired summaries.

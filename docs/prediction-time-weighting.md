# Prediction time weighting

This experiment changes only how the proposed deceleration-propagation method
integrates its existing 10-second speed profiles. It does not enable either
the old global priority hold or the conditional two-stage priority hold.

For elapsed prediction time `t`, the loss contribution is multiplied by:

```text
w(t) = 2 ** (-t / half_life)
```

`--deceleration-time-half-life 0` preserves the current uniform integration.
The first experimental value is `3` seconds.

## Calibration

The source was the saved SUMO 1.28 / Python 3.15.1 / Eval.3 / 300-second
proposed-method run with fixed inputs. `prediction-events.jsonl` contains the
predicted and observed 0.1-second speeds for each completed 10-second window.

- Seeds 1-3 were used to fit inverse-RMSE reliability with an exponential.
- Seeds 4-5 were held out and used only to check whether the fitted decay
  generalised.
- The fitted half-life was 3.253 seconds on Seeds 1-3 and 2.903 seconds on
  Seeds 4-5 (10.8% relative difference).
- The selected value is the training fit rounded to a whole second: 3 seconds.
- At 10 seconds the decision weight is still 0.099, so the full horizon is
  retained rather than cut off.

Reproduce the calibration with:

```bash
python3 scripts/calibrate_prediction_time_weights.py \
  results/formal-deceleration-propagation-eval3-py315-sumo128-fixed-prefix300s-diagnostic-20261025-bbb46e5/eval3
```

## First simulation comparison

Run only the proposed method with the new weight. Keep the agreement hold off:

```bash
python3 scripts/run_thesis_batch.py \
  --cases eval3 \
  --seeds 1 2 3 4 5 \
  --duration 300 \
  --workers 5 \
  --deceleration-active \
  --deceleration-time-half-life 3
```

Compare this run against the same fixed-input current proposal and Yamashita
baseline. A deadband or agreement-hold rule belongs in a later, separate
experiment so that the effect of time weighting remains identifiable.

# Eval3/Eval5 300-second baseline recovery record

This record identifies the ten formally adopted baseline outputs.  The original
15-run batch was interrupted; only the outputs named below are included in the
result commit.  Failed 1.18.0-environment recovery directories, incomplete
original outputs, and all Eval7 outputs are deliberately excluded.

## Environment and acceptance checks

- Python: `.venv-py315-sumo128/bin/python` (3.15.1)
- SUMO and TraCI: `.venv-py315-sumo128/lib/python3.15/site-packages/sumo`
  (1.28.0), supplied by absolute path
- Each adopted manifest has `exit_code: 0` and `source_unchanged: true`.
- Each `evaluation-metrics.json` records 3,000 physical-safety observations
  through 300.0 s, zero collision episodes, and
  `physical_collision_free: true`.
- The manifest's fixed-input SHA-256 was rechecked against the corresponding
  `fixed_inputs/thesis/<case>/seed-<n>.jsonl` file.  All required traces and
  audits are present.

## Adopted Eval3 outputs

| Seed | Adopted output | Recovery provenance |
| --- | --- | --- |
| 1 | `baseline-recovery-eval3-seed1-from180-sumo128-20261026T202000+0900/eval3/seed-1` | resumed at 180 s from the interrupted batch checkpoint |
| 2 | `baseline-recovery-smoke-eval3-seed2-from240-sumo128-20261026T201342+0900/eval3/seed-2` | validated recovery smoke; resumed at 240 s |
| 3 | `baseline-recovery-eval3-seed3-from240-sumo128-20261026T202000+0900/eval3/seed-3` | resumed at 240 s from the interrupted batch checkpoint |
| 4 | `baseline-eval3-eval5-eval7-fixed-300s-default-seeds-20261026T183049+0900/eval3/seed-4` | original batch completed normally |
| 5 | `baseline-eval3-eval5-eval7-fixed-300s-default-seeds-20261026T183049+0900/eval3/seed-5` | original batch completed normally |

## Adopted Eval5 outputs

| Seed | Adopted output | Recovery provenance |
| --- | --- | --- |
| 1 | `baseline-recovery-eval5-seed1-from180-sumo128-20261026T202000+0900/eval5/seed-1` | resumed at 180 s |
| 2 | `baseline-recovery-eval5-seed2-from180-sumo128-20261026T202000+0900/eval5/seed-2` | resumed at 180 s |
| 3 | `baseline-recovery-eval5-seed3-from180-sumo128-20261026T202000+0900/eval5/seed-3` | resumed at 180 s |
| 4 | `baseline-recovery-eval5-seed4-from240-sumo128-20261026T202000+0900/eval5/seed-4` | resumed at 240 s |
| 5 | `baseline-recovery-eval5-seed5-from180-sumo128-20261026T202000+0900/eval5/seed-5` | resumed at 180 s |

All resumed checkpoints contain native SUMO state, controller and agreement
state, fixed-input cursor, random state, and metric accumulators.  The seed-2
smoke was accepted only after its recorded runtime stream demonstrated
continuity from 240.1 s through 300.0 s.

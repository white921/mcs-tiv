# Imported Yamashita (TIVTEP) formal baseline

This is a migration of the already-completed 600-second formal experiment,
not a new simulation.  It is retained as the Yamashita/TIVTEP comparison
baseline, with its original source snapshot lineage (`bbb46e5`).

## Verified preserved properties

All 15 documented runs are present: Eval3 and Eval5 seeds 1--5, and Eval7
seeds 1, 2, 3, 7, and 11.  Every manifest was rechecked at import time for:

- normal completion (`exit_code: 0`) and unchanged source;
- 600.0-second duration;
- Eclipse SUMO 1.28.0 and Python 3.15.1; and
- equality between its manifest fixed-input SHA-256 and the canonical
  `fixed_inputs/thesis/` file.

## Comparison scope and log limitations

The imported experiment follows the earlier logging schema, rather than the
current audited baseline schema.

- Eval3 retains prediction-event traces, but lacks FCD, deceleration audit,
  and SUMO physical-collision audit files.
- Eval5 and Eval7 retain the earlier summary, manifest, controller audit, and
  prediction-event outputs, but lack FCD, vehicle-state/coordinate, conflict,
  negotiation, runtime, deceleration, and SUMO physical-collision audit logs.

Therefore, the imported data are comparable for the preserved aggregate
metrics, fixed inputs, duration, and execution environment.  They are not
comparable for the current trace-level trajectory, negotiation, deceleration,
or independently audited SUMO physical-safety analyses.  No missing audit was
reconstructed after the fact.

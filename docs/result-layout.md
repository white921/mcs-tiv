# Simulation result layout

The canonical destination for new simulation output is `results/runs/`.
The singular `result/` directory is a read-only legacy archive of curated and
handover evidence.

One batch invocation owns one experiment directory. Each independent
case/seed process owns one child directory inside that experiment:

```text
results/runs/<experiment-id>/
  experiment-manifest.json
  runner.log
  summary.json
  <case>/seed-<seed>/
    manifest.json
    stdout.log
    stderr.log
    fcd.xml.gz
    vehicle-states.jsonl
    negotiations.jsonl
    conflicts.jsonl
    prediction-events.jsonl
    evaluation-metrics.json
    checkpoints/
    source/
```

`run_thesis_batch.py` creates a timestamped experiment ID when neither
`--output` nor `--run-name` is supplied. `--run-name` creates a named child of
`results/runs/`. `--output` remains available for temporary or externally
managed storage, but it must still point to a new directory.

The experiment manifest records batch-level intent and completion. A
simulation manifest records exact case, seed, environment, source hashes,
input hashes, generated artifacts, and exit status. A run is valid for commit
only when every intended simulation has `exit_code: 0`, source hashes are
unchanged, and the experiment manifest says `status: completed`.


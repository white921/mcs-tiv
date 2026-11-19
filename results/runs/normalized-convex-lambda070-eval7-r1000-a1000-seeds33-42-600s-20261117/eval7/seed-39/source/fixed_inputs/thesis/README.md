# Fixed thesis vehicle inputs

These committed JSONL files freeze the 600-second vehicle inputs used by
`scripts/run_thesis_batch.py` for Eval.3, Eval.5, and Eval.7.  The first line is
schema metadata.  Each remaining line is one vehicle event in the exact order
used by the scenario runner:

```text
record_type, sequence, depart_time_s, approach, depart_lane, route, vehicle_type
```

Schema version 1 requires contiguous zero-based sequence numbers, 0.1-second
departure times, scenario-valid routes and lanes, and the fixed-nearest Bus
count.  The loader rejects a file when its case, Seed, duration, flows, or Bus
share differs from the command-line run.

The files were generated once from the legacy Seed logic with:

```bash
.venv/bin/python scripts/generate_fixed_vehicle_inputs.py
```

Use `--check` to verify that the committed bytes still match the generator.
Generation consumes the legacy `sample`, route `choice`, unused fixed-mode Bus
`choice`, and independent vehicle-type shuffle in their historical order.
Fixed-allocation Eval.3/5/7 runs with any duration in `(0, 600]` load these
files and use only records whose `depart_time_s` is strictly less than the
effective run limit (`--stop-time` when supplied, otherwise `--duration`).
They make no input-randomness calls.  The manifest records the full-file hash,
prefix duration, prefix event count, and a SHA-256 over the canonical JSONL
vehicle records in that prefix.  The legacy runtime generator remains
available for other evaluations and `--bus-allocation paper-random25`.

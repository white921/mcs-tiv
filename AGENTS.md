# Simulation result commits

- Save every new run under `results/runs/<experiment-id>/`; never add new
  simulation output to the legacy singular `result/` directory.
- One batch invocation owns one experiment directory. One case/seed process
  owns one child directory containing its manifest, logs, traces, FCD, and
  checkpoints. Keep the runner log inside the experiment directory.
- Commit and push a simulation result only after it has ended normally and its
  manifest confirms `exit_code: 0` and `source_unchanged: true`.
- Use one unique output directory per run, and commit only that directory and
  its associated runner log in a dedicated result commit.
- Never push incomplete or failed experiments. Do not include unrelated dirty
  files, source changes, or other result directories in a result commit.

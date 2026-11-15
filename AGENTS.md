# Simulation result commits

## Long-running simulation monitoring

- When the user says `いつも通り監視`, `監視もお願い`, or otherwise requests
  continued monitoring of an Ubuntu/SUMO batch, read
  `docs/experiments/monitoring.md` before starting the monitor.
- Use a Codex thread heartbeat automation for periodic monitoring. Do not keep
  the foreground turn occupied with a shell sleep/poll loop unless the user
  explicitly requests foreground monitoring.
- Treat the heartbeat's SSH readback as the source of truth; never report a
  remembered or locally inferred remote state.

## Worktree lifecycle

- Create a worktree only when concurrent work or a clean isolated experiment
  requires it. Do not keep one checkout per historical branch by default.
- After results and required evidence are preserved and the branch is pushed,
  remove a clean inactive worktree. Keep the branch and remote commit so the
  checkout can be recreated when needed.
- Never remove a worktree with tracked changes, untracked experiment evidence,
  an active process, or an active automation reference.

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

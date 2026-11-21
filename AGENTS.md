# Simulation artifacts and worktrees

## Experiment records

- Create or update one record under `docs/experiments/` for each research
  batch. Record its purpose, conditions, comparison target, source commit,
  output location, limitations, and conclusion. Mark unknowns as unverified.
- Treat manifests and metrics as the numeric source of truth. Do not infer a
  result from a directory name, remembered run, or partial log.
- Classify each run as `smoke`, `diagnostic`, or `formal` before deciding what
  to retain.

## Retention policy

- Smoke runs are transient startup and configuration checks. Do not commit
  their raw output. Delete it after the intended formal run succeeds, keeping
  only a short record when the check is worth documenting.
- Diagnostic runs are exploratory. Delete raw traces after the issue is
  resolved and a durable explanation or regression test exists. Retain only a
  representative diagnostic run that directly supports a research conclusion,
  thesis figure, replay, or non-regression claim.
- Formal experiments must retain their record, manifest, conditions, source
  commit, compact metrics, and selected figures in Git. Do not commit large raw
  artifacts such as FCD, vehicle-state traces, prediction-event streams,
  checkpoints, or per-run source snapshots by default.
- Existing committed results are historical evidence and must not be removed
  merely to reduce repository size.
- Until external artifact storage is selected, keep irreplaceable formal raw
  artifacts outside the repository and mark their storage as pending. Do not
  delete them until a verified copy exists.
- When external storage is used, record the artifact URI, SHA-256, byte size,
  and contents in the experiment record or manifest.
- Never commit or push incomplete or failed runs. Preserve only the failure
  reason, command, source commit, and other compact evidence needed to prevent
  recurrence.

## Worktree lifecycle

- Create a worktree only for concurrent work or a clean isolated experiment.
- Remove an inactive worktree after its unique changes and required evidence
  are preserved. Keep the branch or a local backup commit so it can be
  recreated.
- Never remove a worktree with unreviewed tracked changes, untracked research
  evidence, an active process, or an active monitoring reference.

## Repository maintenance

- Do not run full-history object scans, `git gc`, or full repacks during normal
  work without explicit user approval.
- Prefer targeted history queries by branch and path. This repository disables
  automatic maintenance locally because its historical result packs are large.

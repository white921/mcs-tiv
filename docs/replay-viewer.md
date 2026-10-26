# MCS Replay Viewer

`MCS Replay Viewer` is a local browser application for inspecting a completed
simulation without rerunning SUMO and without generating a new standalone HTML
file for every question.

## Start

Give it the directory containing one seed's `manifest.json` and trace files.

```bash
python3 scripts/mcs_replay_viewer.py \
  results/runs/<experiment-id>/eval3/seed-3
```

The command starts a server bound to `127.0.0.1:8765` and opens the browser.
Use `--port 0` to choose an available port or `--no-open` for a headless host.

## UI contract

- road geometry comes from the exact `.net.xml` copied into the result;
- vehicle pose, dimensions, speed, acceleration, blinkers, and brake lamps come
  from logged values, not from inferred movement;
- previous/next, play/pause, playback rate, timeline slider, keyboard arrows,
  and jump-to-negotiation controls are always available;
- ordinary wheel/two-finger gestures scroll the page; map zoom uses trackpad
  pinch or Ctrl/Command plus wheel so the canvas does not trap scrolling;
- stopped vehicles (`speed < 0.1 m/s`) have a red ring;
- negotiation senders have a pink ring and receivers a purple ring;
- when a negotiation is active, unrelated vehicles remain visible but faint;
- related vehicles do not receive an additional orange ring;
- the event panel joins negotiation records to the closest 0.1-second frame.

The server indexes uncompressed JSONL by byte offset instead of loading all
vehicle frames into browser memory.  This keeps a 600-second diagnostic usable.
Gzipped historical traces are accepted but are loaded into server memory.

## Scope

The current viewer is a single-run replay and diagnosis tool.  A side-by-side
run comparison and restart checkpoints are separate milestones.  See
`docs/replay-log-format.md` for the checkpoint requirements; FCD alone is not a
restart checkpoint.

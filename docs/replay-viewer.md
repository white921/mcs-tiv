# MCS Replay Viewer

`MCS Replay Viewer` is a local browser application for inspecting a completed
simulation without rerunning SUMO and without generating a new standalone HTML
file for every question.

## Start

By default the server indexes every replayable result under `results/`:

```bash
python3 scripts/mcs_replay_viewer.py
```

The command starts a server bound to `127.0.0.1:8765` and opens the browser.
Use `--port 0` to choose an available port or `--no-open` for a headless host.
Passing either a different results root or one seed directory remains supported.

## UI contract

- road geometry comes from the exact `.net.xml` copied into the result;
- vehicle pose, dimensions, speed, acceleration, blinkers, and brake lamps come
  from logged values, not from inferred movement;
- previous/next, play/pause, playback rate, timeline slider, keyboard arrows,
  and jump-to-negotiation controls are always available;
- experiment, Eval, and Seed selectors are populated from local replayable
  manifests; switching them replays saved logs and never reruns SUMO;
- dragging pans the map, and an unmodified vertical wheel gesture zooms around
  the pointer (up to zoom in, down to zoom out);
- horizontal wheel/two-finger gestures move the view, while pinch zooms it;
- stopped vehicles (`speed < 0.1 m/s`) have a red ring;
- negotiation senders have a pink ring and receivers a purple ring;
- when a negotiation is active, unrelated vehicles remain visible but faint;
- related vehicles do not receive an additional orange ring;
- dashed links connect each following vehicle to the leader reported by SUMO;
- the event panel joins negotiation records to the closest 0.1-second frame.
- Eval.3 displays an explicit note that the inherited implementation uses the
  four-arm network with no traffic on the upper approach.

The server indexes uncompressed JSONL by byte offset instead of loading all
vehicle frames into browser memory.  This keeps a 600-second diagnostic usable.
Gzipped historical traces are accepted but are loaded into server memory.

## Scope

The current viewer is a single-run replay and diagnosis tool.  A side-by-side
run comparison and restart checkpoints are separate milestones.  See
`docs/replay-log-format.md` for the checkpoint requirements; FCD alone is not a
restart checkpoint.

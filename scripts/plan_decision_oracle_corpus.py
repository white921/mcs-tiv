#!/usr/bin/env python3
"""Build the fixed 120-event oracle plan from audited natural runs."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path


CASES = {
    "eval3": (1, 2, 3, 4, 5),
    "eval5": (1, 2, 3, 4, 5),
    "eval7": (1, 2, 3, 7, 11),
}


def read_jsonl(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def run_manifests(root):
    found = {}
    for path in sorted(root.rglob("manifest.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        case, seed = value.get("case"), value.get("seed")
        if case not in CASES or seed not in CASES[case]:
            continue
        if value.get("exit_code") != 0 or value.get("source_unchanged") is not True:
            raise ValueError(f"discovery run is not valid: {path}")
        key = (case, int(seed))
        if key in found:
            raise ValueError(f"duplicate discovery run for {key}: {path}")
        found[key] = (path.parent, value)
    return found


def negotiation_path(run_dir):
    candidates = [run_dir / "negotiations.jsonl",
                  run_dir / "negotiations.jsonl.gz"]
    existing = [path for path in candidates if path.is_file()]
    if len(existing) != 1:
        raise ValueError(f"expected one negotiation trace in {run_dir}")
    return existing[0]


def selected_events(trace, count):
    selected = []
    seen = set()
    decision_ordinal = 0
    for record in read_jsonl(trace):
        if record.get("event") != "decision":
            continue
        # The simulator's oracle ordinal advances only after a feasible
        # alternative exists and the TIV/proposal policy actually chooses
        # Accept or Reject.  Physics-only refusals such as
        # ``no_feasible_alternative`` never reach the forceable boundary and
        # therefore cannot be replayed as an Accept/Reject pair.
        if record.get("reason") not in {
                "thesis-tiv-fallback", "deceleration-propagation"}:
            continue
        decision_ordinal += 1
        identity = (
            str(record["receiver_id"]),
            str(record["sender_id"]),
            str(record["desired_path_id"]),
        )
        if identity in seen:
            continue
        seen.add(identity)
        selected.append({
            "ordinal": decision_ordinal,
            "sim_time_s": float(record["sim_time"]),
            "receiver_id": identity[0],
            "sender_id": identity[1],
            "desired_path_id": identity[2],
        })
        if len(selected) == count:
            return selected
    raise ValueError(f"only {len(selected)} unique decisions in {trace}; need {count}")


def build_plan(discoveries, events_per_run=4):
    events = []
    sources = {}
    for origin in ("yamashita", "proposal"):
        runs = run_manifests(discoveries[origin])
        required = {(case, seed) for case, seeds in CASES.items() for seed in seeds}
        missing = sorted(required - set(runs))
        if missing:
            raise ValueError(f"missing {origin} discovery runs: {missing}")
        for case in ("eval3", "eval5", "eval7"):
            for seed in CASES[case]:
                run_dir, manifest = runs[(case, seed)]
                trace = negotiation_path(run_dir)
                sources[f"{origin}:{case}:{seed}"] = {
                    "run_directory": str(run_dir),
                    "trace": str(trace),
                    "git": manifest.get("git"),
                    "fixed_vehicle_input": manifest.get("fixed_vehicle_input"),
                }
                for event in selected_events(trace, events_per_run):
                    events.append({
                        "case": case,
                        "seed": seed,
                        "origin_policy": origin,
                        **event,
                    })
    return {
        "schema": "decision-oracle-plan-v1",
        "selection_rule": (
            "first four unique forceable TIV/proposal Accept/Reject decisions in "
            "natural-log order for each case/origin/seed; physics-only refusals are "
            "excluded and invalid selected events are not replaced"),
        "events_per_run": events_per_run,
        "event_count": len(events),
        "events": events,
        "discovery_sources": sources,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yamashita-discovery", type=Path, required=True)
    parser.add_argument("--proposal-discovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events-per-run", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    if args.events_per_run != 4:
        parser.error("the preregistered corpus requires exactly four events per run")
    plan = build_plan({
        "yamashita": args.yamashita_discovery.resolve(),
        "proposal": args.proposal_discovery.resolve(),
    }, args.events_per_run)
    args.output.write_text(
        json.dumps(plan, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"event_count": plan["event_count"],
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()

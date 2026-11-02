#!/usr/bin/env python3
"""Build the fixed 120-event oracle plan from audited natural runs."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
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


def run_manifests(root, cases=CASES):
    found = {}
    for path in sorted(root.rglob("manifest.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        case, seed = value.get("case"), value.get("seed")
        if case not in cases or seed not in cases[case]:
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


def forceable_events(trace):
    """Return the first record for every forceable negotiation identity."""
    events = []
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
        events.append({
            "ordinal": decision_ordinal,
            "sim_time_s": float(record["sim_time"]),
            "receiver_id": identity[0],
            "sender_id": identity[1],
            "desired_path_id": identity[2],
        })
    return events


def selected_events(trace, count, *, time_start_s=None, time_end_s=None,
                    include_time_end=False, sampling_seed=None,
                    selection_key=""):
    candidates = forceable_events(trace)
    if time_start_s is not None:
        candidates = [
            event for event in candidates
            if float(event["sim_time_s"]) >= time_start_s
            and (float(event["sim_time_s"]) <= time_end_s
                 if include_time_end
                 else float(event["sim_time_s"]) < time_end_s)
        ]
    if len(candidates) < count:
        window = ("all times" if time_start_s is None else
                  f"{time_start_s}..{time_end_s} s")
        raise ValueError(
            f"only {len(candidates)} unique decisions in {trace} "
            f"for {window}; need {count}")
    if sampling_seed is None:
        return candidates[:count]
    seed_material = (
        f"{sampling_seed}|{selection_key}|{time_start_s}|{time_end_s}|"
        f"{int(include_time_end)}").encode("utf-8")
    stable_seed = int.from_bytes(
        hashlib.sha256(seed_material).digest()[:16], "big")
    selected = random.Random(stable_seed).sample(candidates, count)
    return sorted(selected, key=lambda event: event["ordinal"])


def build_plan(discoveries, events_per_run=4, cases=CASES, *,
               time_start_s=None, time_end_s=None, include_time_end=False,
               sampling_seed=None):
    events = []
    sources = {}
    for origin in ("yamashita", "proposal"):
        runs = run_manifests(discoveries[origin], cases)
        required = {(case, seed) for case, seeds in cases.items() for seed in seeds}
        missing = sorted(required - set(runs))
        if missing:
            raise ValueError(f"missing {origin} discovery runs: {missing}")
        for case in ("eval3", "eval5", "eval7"):
            for seed in cases[case]:
                run_dir, manifest = runs[(case, seed)]
                trace = negotiation_path(run_dir)
                sources[f"{origin}:{case}:{seed}"] = {
                    "run_directory": str(run_dir),
                    "trace": str(trace),
                    "git": manifest.get("git"),
                    "fixed_vehicle_input": manifest.get("fixed_vehicle_input"),
                }
                selection_key = f"{origin}:{case}:{seed}"
                for event in selected_events(
                        trace, events_per_run,
                        time_start_s=time_start_s,
                        time_end_s=time_end_s,
                        include_time_end=include_time_end,
                        sampling_seed=sampling_seed,
                        selection_key=selection_key):
                    events.append({
                        "case": case,
                        "seed": seed,
                        "origin_policy": origin,
                        **event,
                    })
    stratified = time_start_s is not None
    if stratified:
        end_operator = "<=" if include_time_end else "<"
        selection_rule = (
            f"four unique forceable TIV/proposal Accept/Reject decisions "
            f"sampled without replacement per case/origin/seed from "
            f"{time_start_s} <= sim_time {end_operator} {time_end_s} s "
            f"using deterministic seed {sampling_seed}; physics-only refusals "
            "are excluded and invalid selected events are not replaced")
    else:
        selection_rule = (
            "first four unique forceable TIV/proposal Accept/Reject decisions in "
            "natural-log order for each case/origin/seed; physics-only refusals "
            "are excluded and invalid selected events are not replaced")
    return {
        "schema": "decision-oracle-plan-v1",
        "selection_rule": selection_rule,
        "selection": {
            "method": ("deterministic_random_without_replacement"
                       if stratified else "first_unique_in_natural_order"),
            "time_start_s": time_start_s,
            "time_end_s": time_end_s,
            "include_time_end": bool(include_time_end),
            "sampling_seed": sampling_seed,
        },
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
    parser.add_argument(
        "--seeds", type=int, nargs=5,
        help="five preregistered seeds shared by Eval.3/5/7")
    parser.add_argument("--time-start", type=float)
    parser.add_argument("--time-end", type=float)
    parser.add_argument("--include-time-end", action="store_true")
    parser.add_argument("--sampling-seed", type=int)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    if args.events_per_run != 4:
        parser.error("the preregistered corpus requires exactly four events per run")
    if args.seeds is not None and (
            len(set(args.seeds)) != 5 or any(seed < 0 for seed in args.seeds)):
        parser.error("--seeds must contain five unique non-negative integers")
    has_start, has_end = args.time_start is not None, args.time_end is not None
    if has_start != has_end:
        parser.error("--time-start and --time-end must be provided together")
    if has_start:
        if (not math.isfinite(args.time_start)
                or not math.isfinite(args.time_end)
                or args.time_start < 0
                or args.time_end <= args.time_start):
            parser.error("time window must be finite, non-negative, and increasing")
        if args.sampling_seed is None:
            parser.error("--sampling-seed is required for a time window")
    elif args.include_time_end or args.sampling_seed is not None:
        parser.error("time-window options require --time-start and --time-end")
    cases = (CASES if args.seeds is None else
             {case: tuple(args.seeds) for case in CASES})
    plan = build_plan({
        "yamashita": args.yamashita_discovery.resolve(),
        "proposal": args.proposal_discovery.resolve(),
    }, args.events_per_run, cases,
        time_start_s=args.time_start,
        time_end_s=args.time_end,
        include_time_end=args.include_time_end,
        sampling_seed=args.sampling_seed)
    args.output.write_text(
        json.dumps(plan, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"event_count": plan["event_count"],
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()

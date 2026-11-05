#!/usr/bin/env python3
"""Freeze the eight preregistered oracle-aligned v2 holdout plans."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from plan_decision_oracle_corpus import CASES, build_plan  # noqa: E402
from run_thesis_batch import git_metadata  # noqa: E402


SEED_GROUPS = ((23, 24, 25, 26, 27), (28, 29, 30, 31, 32))
WINDOWS = (
    ("0-100", 0.0, 100.0, False),
    ("100-160", 100.0, 160.0, False),
    ("160-220", 160.0, 220.0, False),
    ("220-290", 220.0, 290.0, True),
)
SAMPLING_SEED = 20261105
DISCOVERY_SOURCE_COMMIT = "540c61e033fa793c9f7ed102b8e1cc004d682841"


def serialize(value: dict) -> bytes:
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()


def validate_discovery(root: Path, origin: str) -> dict:
    path = root / "experiment-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected_method = (
        str(manifest.get("method", "")).startswith("yamashita")
        if origin == "yamashita"
        else manifest.get("method") == "deceleration-propagation")
    checks = {
        "status": manifest.get("status") == "completed",
        "completed_simulations": manifest.get("completed_simulations") == 30,
        "failed_simulations": manifest.get("failed_simulations") == 0,
        "duration_s": float(manifest.get("duration_s", -1)) == 300.0,
        "workers": manifest.get("workers") == 10,
        "cases": tuple(manifest.get("cases", ())) == tuple(CASES),
        "seeds": sorted({
            int(task["seed"]) for task in manifest.get("tasks", ())
        }) == list(range(23, 33)),
        "source_commit": (
            manifest.get("git", {}).get("commit") == DISCOVERY_SOURCE_COMMIT),
        "git_clean": manifest.get("git", {}).get("dirty") is False,
        "method": expected_method,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(
            f"invalid {origin} discovery batch {path}: {', '.join(failed)}")
    return {
        "manifest": str(path.resolve()),
        "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_commit": DISCOVERY_SOURCE_COMMIT,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yamashita-discovery", type=Path, required=True)
    parser.add_argument("--proposal-discovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output directory already exists")
    args.output.mkdir(parents=True)
    discoveries = {
        "yamashita": args.yamashita_discovery.resolve(),
        "proposal": args.proposal_discovery.resolve(),
    }
    try:
        discovery_audit = {
            origin: validate_discovery(root, origin)
            for origin, root in discoveries.items()
        }
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    hashes = {}
    plans = []
    for seeds in SEED_GROUPS:
        cases = {case: seeds for case in CASES}
        for window, start, end, include_end in WINDOWS:
            plan = build_plan(
                discoveries, 4, cases,
                time_start_s=start,
                time_end_s=end,
                include_time_end=include_end,
                sampling_seed=SAMPLING_SEED)
            if plan["event_count"] != 120:
                raise ValueError(
                    f"unexpected event count for {seeds}:{window}: "
                    f"{plan['event_count']}")
            name = f"oracle-v2-{seeds[0]}-{seeds[-1]}-t{window}.json"
            path = args.output / name
            payload = serialize(plan)
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            key = f"{seeds[0]}-{seeds[-1]}:{window}"
            hashes[key] = digest
            plans.append({
                "seed_min": seeds[0], "seed_max": seeds[-1],
                "window": window, "time_start_s": start,
                "time_end_s": end, "include_time_end": include_end,
                "events": plan["event_count"], "file": name,
                "sha256": digest,
            })
    (args.output / "expected-plan-hashes.json").write_text(
        json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema": "oracle-aligned-v2-holdout-plans-v1",
        "status": "frozen",
        "outcomes_inspected": False,
        "sampling_seed": SAMPLING_SEED,
        "git": git_metadata(),
        "discovery_audit": discovery_audit,
        "yamashita_discovery": str(discoveries["yamashita"]),
        "proposal_discovery": str(discoveries["proposal"]),
        "plan_count": len(plans),
        "event_count": sum(plan["events"] for plan in plans),
        "plans": plans,
    }
    (args.output / "plan-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "plans": len(plans), "events": manifest["event_count"],
        "hashes": hashes,
    }, indent=2))


if __name__ == "__main__":
    main()

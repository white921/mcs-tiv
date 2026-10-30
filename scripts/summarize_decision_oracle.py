"""Validate and aggregate a completed decision-oracle corpus.

This deliberately refuses partial event directories.  It is run only after
the branch runner has produced both 10-second branch manifests and metrics.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
import decision_oracle


def read_event(path):
    manifest = path / "manifest.json"
    if not manifest.is_file():
        raise ValueError(f"missing event manifest: {path}")
    event = json.loads(manifest.read_text(encoding="utf-8"))
    if event.get("schema") != "decision-oracle-event-v1":
        raise ValueError(f"unsupported event manifest: {path}")
    for branch in ("accept", "reject"):
        value = event.get("branches", {}).get(branch, {})
        if value.get("completed") is not True:
            raise ValueError(f"incomplete {branch} branch: {path}")
        if not value.get("restore_fingerprint_match"):
            raise ValueError(f"restore mismatch in {branch}: {path}")
    accept, reject = event["branches"]["accept"]["metrics"], event["branches"]["reject"]["metrics"]
    label = decision_oracle.oracle_choice(accept, reject, event.get("tie_tolerance_s", decision_oracle.TIE_TOLERANCE_S))
    scores = {name: decision_oracle.score_policy(choice, accept, reject, label)
              for name, choice in event.get("policy_choices", {}).items()}
    return {"event_id": event.get("event_id"), "oracle": label, "policy_scores": scores,
            "predictor_errors": event.get("predictor_errors", {})}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", type=Path)
    args = parser.parse_args()
    root = args.experiment.resolve()
    events = [read_event(path) for path in sorted(root.glob("events/*")) if path.is_dir()]
    if not events:
        raise ValueError("no event directories found")
    output = {"schema": "decision-oracle-summary-v1", "summary": decision_oracle.summarize(events),
              "events": events}
    (root / "summary.json").write_text(json.dumps(output, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(output["summary"], allow_nan=False))


if __name__ == "__main__":
    main()

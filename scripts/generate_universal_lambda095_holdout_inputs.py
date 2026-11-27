#!/usr/bin/env python3
"""Generate fixed inputs for the preregistered universal-lambda holdout."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_fixed_vehicle_inputs import (  # noqa: E402
    generate_eval7_flow_sweep_records,
    generate_records,
    serialize,
)


SEEDS = tuple(range(23, 33))
GENERATION_PYTHON = "3.15.1"
CONDITIONS = {
    "eval3-500": (
        "eval3",
        {"left": 500, "bottom": 500, "right": 500},
    ),
    "eval5-300": (
        "eval5",
        {"left": 300, "bottom": 300, "right": 300, "top": 300},
    ),
    "eval7-1000": (
        "eval7",
        {"requesting": 1000, "accepting": 1000},
    ),
}


def expected_files(output: Path):
    for condition, (case, flows) in CONDITIONS.items():
        for seed in SEEDS:
            path = output / condition / f"seed-{seed}.jsonl"
            if case == "eval7":
                records = generate_eval7_flow_sweep_records(
                    seed, flows["requesting"], flows["accepting"]
                )
            else:
                records = generate_records(case, seed, flows)
            records[0]["generated_with_python"] = GENERATION_PYTHON
            yield path, serialize(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            ROOT
            / "fixed_inputs"
            / "thesis"
            / "universal-lambda095-holdout"
        ),
    )
    parser.add_argument(
        "--check", action="store_true", help="fail if committed files differ"
    )
    args = parser.parse_args()

    failures = []
    for path, expected in expected_files(args.output):
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                failures.append(str(path))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8")
    if failures:
        print("fixed input mismatch:", *failures, sep="\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

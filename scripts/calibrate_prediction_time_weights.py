#!/usr/bin/env python3
"""Calibrate an exponential time weight from saved prediction event logs."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def collect_errors(root: Path, seeds: list[int]) -> list[list[float]]:
    buckets = [[] for _ in range(11)]
    for seed in seeds:
        path = root / f"seed-{seed}" / "prediction-events.jsonl"
        if not path.is_file():
            raise FileNotFoundError(path)
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if not event.get("horizon_complete"):
                    continue
                for vehicle in event.get("vehicles", {}).values():
                    predicted = vehicle.get("predicted_speed_mps") or []
                    actual = vehicle.get("actual_speed_mps") or []
                    for index, (observed, expected) in enumerate(
                            zip(actual, predicted)):
                        if observed is None:
                            continue
                        bucket = min(10, index // 10)
                        buckets[bucket].append(float(observed) - float(expected))
    if not all(buckets):
        raise ValueError("each one-second prediction bucket needs observed samples")
    return buckets


def summarise(buckets: list[list[float]]) -> list[dict]:
    result = []
    for second, values in enumerate(buckets):
        result.append({
            "second": second,
            "samples": len(values),
            "speed_mae_mps": sum(abs(value) for value in values) / len(values),
            "speed_rmse_mps": math.sqrt(
                sum(value * value for value in values) / len(values)),
            "signed_error_mps": sum(values) / len(values),
        })
    return result


def fit_half_life(summary: list[dict]) -> float:
    """Fit inverse-RMSE reliability with an origin-anchored exponential."""
    base = summary[0]["speed_rmse_mps"]
    numerator = 0.0
    denominator = 0.0
    for item in summary[1:]:
        second = float(item["second"])
        reliability_log2 = math.log2(base / item["speed_rmse_mps"])
        numerator += second * reliability_log2
        denominator += second * second
    slope = numerator / denominator
    if slope >= 0:
        raise ValueError("prediction error does not increase with horizon")
    return -1.0 / slope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_root", type=Path,
                        help="directory containing seed-N/prediction-events.jsonl")
    parser.add_argument("--train-seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--validation-seeds", type=int, nargs="+", default=[4, 5])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    train = summarise(collect_errors(args.result_root, args.train_seeds))
    validation = summarise(
        collect_errors(args.result_root, args.validation_seeds))
    train_half_life = fit_half_life(train)
    validation_half_life = fit_half_life(validation)
    selected = max(1.0, round(train_half_life))
    result = {
        "method": "inverse-RMSE reliability fitted by exponential half-life",
        "training_seeds": args.train_seeds,
        "validation_seeds": args.validation_seeds,
        "training": train,
        "validation": validation,
        "fitted_training_half_life_s": train_half_life,
        "fitted_validation_half_life_s": validation_half_life,
        "selected_half_life_s": selected,
        "weight_at_10s": 2 ** (-10 / selected),
        "validation_relative_difference": abs(
            validation_half_life - train_half_life) / train_half_life,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

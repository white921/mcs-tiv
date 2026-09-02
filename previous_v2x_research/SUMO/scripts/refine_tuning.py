#!/usr/bin/env python3

import argparse
import json
import os


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a refined controller sweep around a top-ranked tuning result"
    )
    parser.add_argument("ranking_json", help="Path to ranking.json from tune_controller.py")
    parser.add_argument(
        "--sweep-config",
        default=os.path.join(os.path.dirname(__file__), "controller_sweep.json"),
        help="Original sweep definition JSON",
    )
    parser.add_argument(
        "--output-dir",
        default="out/tuning_refined",
        help="Directory for refined base config and sweep config",
    )
    parser.add_argument(
        "--top-index",
        type=int,
        default=0,
        help="Index within successful results sorted by score descending",
    )
    parser.add_argument(
        "--shrink-factor",
        type=float,
        default=0.5,
        help="Scale factor for numeric sweep step sizes",
    )
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def dump_json(path, payload):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)


def is_numeric_sequence(values):
    return all(isinstance(value, (int, float)) for value in values)


def refined_values(best_value, original_values, shrink_factor):
    unique_values = sorted(set(float(value) for value in original_values))
    if len(unique_values) == 1:
        return [unique_values[0]]

    closest_distance = min(abs(best_value - candidate) for candidate in unique_values if candidate != best_value)
    step = closest_distance * shrink_factor
    if step == 0.0:
        step = min(
            abs(unique_values[index + 1] - unique_values[index])
            for index in range(len(unique_values) - 1)
        ) * shrink_factor

    values = [best_value - step, best_value, best_value + step]
    rounded = sorted({round(value, 6) for value in values})
    return rounded


def main():
    args = parse_args()
    ranking = load_json(args.ranking_json)
    sweep = load_json(args.sweep_config)

    successful = [result for result in ranking if result.get("status") == "ok"]
    successful.sort(
        key=lambda item: item.get("ranking_score", item["evaluation"]["paper_alignment_score"]),
        reverse=True,
    )
    if not successful:
        raise SystemExit("No successful tuning results found in ranking.json")
    if args.top_index < 0 or args.top_index >= len(successful):
        raise SystemExit("top-index is out of range for successful results")

    chosen = successful[args.top_index]
    best_config = load_json(chosen["config_path"])
    refined_sweep = {"parameters": {}}

    for name, original_values in sweep.get("parameters", {}).items():
        best_value = best_config.get(name)
        if best_value is None:
            continue

        if is_numeric_sequence(original_values) and isinstance(best_value, (int, float)):
            refined_sweep["parameters"][name] = refined_values(
                float(best_value), original_values, args.shrink_factor
            )
        else:
            refined_sweep["parameters"][name] = [best_value]

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    base_config_path = os.path.join(output_dir, "controller_params_refined_base.json")
    sweep_config_path = os.path.join(output_dir, "controller_sweep_refined.json")
    metadata_path = os.path.join(output_dir, "refinement_source.json")

    dump_json(base_config_path, best_config)
    dump_json(sweep_config_path, refined_sweep)
    dump_json(
        metadata_path,
        {
            "chosen_variant_id": chosen["variant_id"],
            "chosen_score": chosen["evaluation"]["paper_alignment_score"],
            "chosen_params": chosen["applied_params"],
            "chosen_deltas": chosen["evaluation"]["deltas"],
            "source_ranking_json": os.path.abspath(args.ranking_json),
            "source_sweep_config": os.path.abspath(args.sweep_config),
            "shrink_factor": args.shrink_factor,
        },
    )

    print(f"saved refined base config to {base_config_path}")
    print(f"saved refined sweep config to {sweep_config_path}")
    print(f"saved refinement metadata to {metadata_path}")


if __name__ == "__main__":
    main()

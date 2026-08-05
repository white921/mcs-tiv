#!/usr/bin/env python3

import argparse
import json
import os


FOCUS_RULES = {
    "p1_accel_threshold": {"step": 0.05, "count": 3},
    "p2_activate_ratio": {"step": 0.05, "count": 3},
    "p3_deactivate_ratio": {"step": 0.05, "count": 3},
    "k_r": {"step": 0.01, "count": 3},
    "k_m2": {"step": 0.01, "count": 3},
    "t_gap_r": {"step": 0.1, "count": 3},
    "t_gap_m": {"step": 0.1, "count": 3},
    "compensation_gain": {"step": 0.05, "count": 3},
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a focused fine-tuning sweep around a controller parameter set"
    )
    parser.add_argument("base_config", help="Controller parameter JSON to center the focus sweep on")
    parser.add_argument(
        "--output",
        default="controller_sweep_focus.json",
        help="Output path for focused sweep JSON",
    )
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def dump_json(path, payload):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)


def generate_values(center, step, count):
    if count != 3:
        raise ValueError("Only 3-point focused sweeps are supported")
    values = [center - step, center, center + step]
    return sorted({round(value, 6) for value in values})


def main():
    args = parse_args()
    config = load_json(args.base_config)

    sweep = {"parameters": {}}
    for name, rule in FOCUS_RULES.items():
        if name not in config:
            continue
        center = float(config[name])
        sweep["parameters"][name] = generate_values(
            center, float(rule["step"]), int(rule["count"])
        )

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    dump_json(output_path, sweep)
    print(f"saved focused sweep to {output_path}")


if __name__ == "__main__":
    main()

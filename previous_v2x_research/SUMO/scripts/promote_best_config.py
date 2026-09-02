#!/usr/bin/env python3

import argparse
import json
import os
import shutil


def parse_args():
    parser = argparse.ArgumentParser(
        description="Promote a tuned controller config to the default controller_params.json"
    )
    parser.add_argument(
        "best_config_json",
        help="Path to the chosen controller parameter JSON",
    )
    parser.add_argument(
        "--target",
        default=os.path.join(os.path.dirname(__file__), "controller_params.json"),
        help="Target controller parameter JSON to overwrite",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Write a .bak copy of the previous target file before replacing it",
    )
    return parser.parse_args()


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def dump_json(path, payload):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)


def main():
    args = parse_args()
    best_config = load_json(args.best_config_json)

    target_path = os.path.abspath(args.target)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    if args.backup and os.path.exists(target_path):
        backup_path = f"{target_path}.bak"
        shutil.copy2(target_path, backup_path)
        print(f"saved backup to {backup_path}")

    dump_json(target_path, best_config)
    print(f"promoted best config to {target_path}")


if __name__ == "__main__":
    main()

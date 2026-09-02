#!/usr/bin/env python3
"""Compare an ideal direct-control run with an MQTT V2C run.

The two runs use the same SUMO scenario and controller parameters.  Therefore
the reported differences isolate the effect of the inserted application-level
communication path under the selected network condition.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare direct-control and MQTT V2C SUMO summaries"
    )
    parser.add_argument("direct_summary_json")
    parser.add_argument("mqtt_summary_json")
    parser.add_argument("--output-json", help="Optional path for the comparison JSON")
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as input_file:
        return json.load(input_file)


def compare_number_maps(
    direct: dict[str, Any], mqtt: dict[str, Any]
) -> dict[str, dict[str, float | None]]:
    comparison: dict[str, dict[str, float | None]] = {}
    for key in sorted(set(direct) | set(mqtt)):
        direct_value = direct.get(key)
        mqtt_value = mqtt.get(key)
        if isinstance(direct_value, (int, float)) and isinstance(mqtt_value, (int, float)):
            delta: float | None = round(mqtt_value - direct_value, 4)
        else:
            delta = None
        comparison[key] = {
            "direct": direct_value,
            "mqtt": mqtt_value,
            "mqtt_minus_direct": delta,
        }
    return comparison


def compare_summaries(
    direct_summary: dict[str, Any], mqtt_summary: dict[str, Any]
) -> dict[str, Any]:
    direct_metrics = direct_summary.get("metrics", {})
    mqtt_metrics = mqtt_summary.get("metrics", {})
    direct_metrics = {
        key: value for key, value in direct_metrics.items() if key != "samples"
    }
    mqtt_metrics = {
        key: value for key, value in mqtt_metrics.items() if key != "samples"
    }
    return {
        "experiment": {
            "direct": "SUMO and controller communicate by in-process function call",
            "mqtt": "SUMO vehicle adapter and cloud controller communicate through MQTT",
            "delta_definition": "mqtt_minus_direct",
        },
        "phase_time_seconds": compare_number_maps(
            direct_summary.get("phases", {}), mqtt_summary.get("phases", {})
        ),
        "event_time_seconds": compare_number_maps(
            direct_summary.get("events", {}), mqtt_summary.get("events", {})
        ),
        "metrics": compare_number_maps(direct_metrics, mqtt_metrics),
        "mqtt_communication": mqtt_summary.get("communication", {}),
    }


def main() -> None:
    args = parse_args()
    result = compare_summaries(
        load_json(args.direct_summary_json), load_json(args.mqtt_summary_json)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()

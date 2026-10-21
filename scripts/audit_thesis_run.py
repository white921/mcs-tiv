"""Read-only audit of a finished isolated simulation; JSON output is optional."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def audit_run(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    statistics = directory / "source" / "junction" / "statistics"
    rows = list(csv.reader((statistics / "acceptance_three.csv").open()))
    summary = next(row for row in rows if row and row[0] == "All")
    stats = {}
    vehicle_ids = defaultdict(set)
    last_time = None
    samples = 0
    for event, element in ET.iterparse(statistics / "sumoStat.xml", events=("end",)):
        if element.tag == "timestep":
            last_time = float(element.attrib["time"])
            element.clear()
        elif element.tag == "vehicle":
            kind = element.attrib["type"]
            if kind not in stats:
                stats[kind] = {"samples": 0, "maximum_speed": 0.0,
                               "maximum_acceleration": float("-inf"),
                               "minimum_acceleration": float("inf"),
                               "limit_violation_samples": 0}
            item = stats[kind]
            speed = float(element.attrib["speed"])
            accel = float(element.attrib["acceleration"])
            vmax, amax, decel = (11.11, 1, 3) if "bus" in kind else (13.89, 3, 5)
            item["samples"] += 1
            item["maximum_speed"] = max(item["maximum_speed"], speed)
            item["maximum_acceleration"] = max(item["maximum_acceleration"], accel)
            item["minimum_acceleration"] = min(item["minimum_acceleration"], accel)
            # FCD default rounds to 2 decimals.
            if speed > vmax + .011 or accel > amax + .011 or accel < -decel - .011:
                item["limit_violation_samples"] += 1
            vehicle_ids[kind].add(element.attrib["id"])
            samples += 1
            element.clear()
    for kind, item in stats.items():
        item["unique_inserted_vehicles"] = len(vehicle_ids[kind])
    expected_end = manifest["stop_time"] - .1  # SUMO FCD is logged before next step.
    log = (directory / "stderr.log").read_text()
    return {"complete_600s_case": manifest["stop_time"] == 600 and
            last_time is not None and abs(last_time - expected_end) < .011,
            "last_fcd_time": last_time, "vehicle_time_samples": samples,
            "csv_all_speed_mps": float(summary[4]),
            "per_type_observed_limits": stats,
            "traceback_or_exit_hook_error": "Traceback" in log or "Error in atexit" in log,
            "sumo_collision_warning_lines": sum("collision" in line.lower()
                and ("warning" in line.lower() or "error" in line.lower()) for line in log.splitlines()),
            "published_reference": {"mean_of_five_seeds_mps": 7.4159,
                "single_seed_not_an_equivalence_test": True},
            "caution": "No SUMO collision warnings does not prove collision-free operation; inherited collision.action=none."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(audit_run(args.directory), indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(result + "\n")
    print(result)

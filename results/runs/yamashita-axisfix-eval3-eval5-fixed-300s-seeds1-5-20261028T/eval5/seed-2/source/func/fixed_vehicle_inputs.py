"""Load and validate versioned, deterministic vehicle input schedules."""

from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path


SCHEMA_VERSION = 1

CASE_SPECS = {
    "eval3": {
        "scenario": "t_junction",
        "approach_order": ("bottom", "left", "right"),
        "routes": {
            "left": ("LR", "LB"),
            "bottom": ("BR", "BL"),
            "right": ("RL", "RB"),
        },
        "depart_lanes": {"left": "0", "bottom": "0", "right": "0"},
    },
    "eval5": {
        "scenario": "four_way_junction",
        "approach_order": ("bottom", "left", "right", "top"),
        "routes": {
            "left": ("LR", "LB", "LT"),
            "bottom": ("BR", "BL"),
            "right": ("RL", "RB", "RT"),
            "top": ("TL", "TR"),
        },
        "depart_lanes": {"left": "0", "bottom": "0", "right": "0", "top": "0"},
    },
    "eval7": {
        "scenario": "merge",
        "approach_order": ("accepting", "requesting"),
        "routes": {"accepting": ("main",), "requesting": ("main",)},
        "depart_lanes": {"accepting": "1", "requesting": "0"},
    },
}

METADATA_KEYS = {
    "record_type", "schema_version", "case", "seed", "duration_s", "scenario",
    "flows_vph", "bus_share", "bus_allocation", "generated_with_python",
}
EVENT_KEYS = {
    "record_type", "sequence", "depart_time_s", "approach", "depart_lane",
    "route", "vehicle_type",
}


class FixedVehicleSchedule:
    """Validated fixed schedule with per-approach queues for scenario runners."""

    def __init__(self, path, metadata, events, prefix_duration_s):
        self.path = Path(path)
        self.metadata = metadata
        self.all_events = tuple(events)
        self.prefix_duration_s = prefix_duration_s
        self.events = tuple(
            event for event in events if event["depart_time_s"] < prefix_duration_s
        )
        prefix_bytes = "".join(
            json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n"
            for event in self.events
        ).encode("utf-8")
        self.prefix_sha256 = hashlib.sha256(prefix_bytes).hexdigest()
        grouped = defaultdict(deque)
        for event in self.events:
            grouped[event["approach"]].append(event)
        self._events_by_approach = grouped

    def departure_times(self, approach):
        return [event["depart_time_s"] for event in self.events if event["approach"] == approach]

    def pop(self, approach, depart_time_s):
        try:
            event = self._events_by_approach[approach].popleft()
        except IndexError as error:
            raise ValueError(f"fixed input has no remaining {approach} event") from error
        if event["depart_time_s"] != depart_time_s:
            raise ValueError(
                f"fixed input expected {approach} at {event['depart_time_s']}, got {depart_time_s}"
            )
        return event


def _load_records(path):
    records = []
    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank lines are not allowed")
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error.msg}") from error
    if not records:
        raise ValueError(f"{path}: fixed input is empty")
    return records


def _validate_metadata(metadata, path):
    if set(metadata) != METADATA_KEYS:
        raise ValueError(f"{path}: metadata keys do not match schema {SCHEMA_VERSION}")
    if metadata["record_type"] != "metadata":
        raise ValueError(f"{path}: first record must be metadata")
    if metadata["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"{path}: unsupported schema version {metadata['schema_version']}")
    if metadata["case"] not in CASE_SPECS:
        raise ValueError(f"{path}: unsupported case {metadata['case']}")
    spec = CASE_SPECS[metadata["case"]]
    if metadata["scenario"] != spec["scenario"]:
        raise ValueError(f"{path}: scenario does not match {metadata['case']}")
    if metadata["duration_s"] != 600.0:
        raise ValueError(f"{path}: fixed thesis input must cover 600 seconds")
    if metadata["bus_allocation"] != "fixed-nearest":
        raise ValueError(f"{path}: unsupported bus allocation")
    if not 0 <= metadata["bus_share"] <= 1:
        raise ValueError(f"{path}: bus_share must be between 0 and 1")
    if set(metadata["flows_vph"]) != set(spec["routes"]):
        raise ValueError(f"{path}: flow approaches do not match scenario")
    if any(not isinstance(flow, int) or flow < 0 for flow in metadata["flows_vph"].values()):
        raise ValueError(f"{path}: flows must be non-negative integers")


def _validate_events(metadata, events, path):
    spec = CASE_SPECS[metadata["case"]]
    approach_rank = {name: index for index, name in enumerate(spec["approach_order"])}
    expected_counts = {
        approach: int(metadata["duration_s"] / 3600 * flow)
        for approach, flow in metadata["flows_vph"].items()
    }
    actual_counts = Counter()
    previous_key = None
    for sequence, event in enumerate(events):
        if set(event) != EVENT_KEYS:
            raise ValueError(f"{path}: event {sequence} keys do not match schema {SCHEMA_VERSION}")
        if event["record_type"] != "vehicle" or event["sequence"] != sequence:
            raise ValueError(f"{path}: event sequence must be contiguous from zero")
        approach = event["approach"]
        if approach not in spec["routes"]:
            raise ValueError(f"{path}: event {sequence} has invalid approach {approach}")
        if event["depart_lane"] != spec["depart_lanes"][approach]:
            raise ValueError(f"{path}: event {sequence} has invalid departure lane")
        if event["route"] not in spec["routes"][approach]:
            raise ValueError(f"{path}: event {sequence} has invalid route {event['route']}")
        if event["vehicle_type"] not in ("Car", "Bus"):
            raise ValueError(f"{path}: event {sequence} has invalid vehicle type")
        depart_time = event["depart_time_s"]
        if not isinstance(depart_time, (int, float)) or not 0 < depart_time < metadata["duration_s"]:
            raise ValueError(f"{path}: event {sequence} has invalid departure time")
        if round(depart_time * 10) != depart_time * 10:
            raise ValueError(f"{path}: event {sequence} is not aligned to a 0.1-second step")
        sort_key = (depart_time, approach_rank[approach])
        if previous_key is not None and sort_key <= previous_key:
            raise ValueError(f"{path}: events are not in stable runtime order")
        previous_key = sort_key
        actual_counts[approach] += 1

    if dict(actual_counts) != expected_counts:
        raise ValueError(
            f"{path}: approach counts {dict(actual_counts)} do not match {expected_counts}"
        )
    bus_count = sum(event["vehicle_type"] == "Bus" for event in events)
    expected_bus_count = int(len(events) * metadata["bus_share"] + 0.5)
    if bus_count != expected_bus_count:
        raise ValueError(
            f"{path}: Bus count {bus_count} does not match nearest-share count {expected_bus_count}"
        )


def load_fixed_vehicle_input(
    path,
    *,
    expected_case=None,
    expected_seed=None,
    expected_duration_s=None,
    expected_flows_vph=None,
    expected_bus_share=None,
    prefix_duration_s=None,
):
    """Load a fixed schedule and reject schema or runtime-condition mismatches."""
    records = _load_records(path)
    metadata, events = records[0], records[1:]
    _validate_metadata(metadata, path)
    _validate_events(metadata, events, path)

    expectations = {
        "case": expected_case,
        "seed": int(expected_seed) if expected_seed is not None else None,
        "duration_s": float(expected_duration_s) if expected_duration_s is not None else None,
        "flows_vph": expected_flows_vph,
        "bus_share": expected_bus_share,
    }
    for key, expected in expectations.items():
        if expected is not None and metadata[key] != expected:
            raise ValueError(f"{path}: {key}={metadata[key]!r}, expected {expected!r}")
    if prefix_duration_s is None:
        prefix_duration_s = metadata["duration_s"]
    prefix_duration_s = float(prefix_duration_s)
    if not 0 < prefix_duration_s <= metadata["duration_s"]:
        raise ValueError(
            f"{path}: prefix duration must be in (0, {metadata['duration_s']}]"
        )
    return FixedVehicleSchedule(path, metadata, events, prefix_duration_s)

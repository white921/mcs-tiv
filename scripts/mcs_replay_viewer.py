#!/usr/bin/env python3
"""Serve a local, reusable replay UI for one MCS simulation result."""

from __future__ import annotations

import argparse
import datetime
import gzip
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "tools" / "replay-viewer"


class FrameStore:
    """Random access to JSONL frames without loading a large run into memory."""

    def __init__(self, path: Path):
        self.path = path
        self.offsets: list[int] = []
        self.times: list[float] = []
        self._compressed_records: list[dict] | None = None
        if path.suffix == ".gz":
            self._compressed_records = []
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    self._compressed_records.append(record)
                    self.times.append(float(record["sim_time"]))
        else:
            with path.open("rb") as stream:
                while True:
                    offset = stream.tell()
                    line = stream.readline()
                    if not line:
                        break
                    if not line.strip():
                        continue
                    self.offsets.append(offset)
                    record = json.loads(line)
                    self.times.append(float(record["sim_time"]))

    def __len__(self):
        return len(self.times)

    def get(self, index: int) -> dict:
        if not 0 <= index < len(self):
            raise IndexError(index)
        if self._compressed_records is not None:
            return self._compressed_records[index]
        with self.path.open("rb") as stream:
            stream.seek(self.offsets[index])
            return json.loads(stream.readline())


def find_trace(run_dir: Path, base_name: str, required=False) -> Path | None:
    names = [base_name]
    if base_name.endswith(".jsonl"):
        names.insert(0, f"{base_name.removesuffix('.jsonl')}-full.jsonl")
    for name in names:
        for suffix in ("", ".gz"):
            candidate = run_dir / f"{name}{suffix}"
            if candidate.is_file():
                return candidate
    if required:
        raise FileNotFoundError(f"{base_name} not found under {run_dir}")
    return None


def read_jsonl(path: Path | None) -> list[dict]:
    if path is None:
        return []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


NETWORK_BY_CASE = {
    "eval3": "junction_three.net.xml",
    "eval4": "junction_four.net.xml",
    "eval5": "junction_four.net.xml",
    "eval6": "threeLane.net.xml",
    "eval7": "threeLane.net.xml",
}


def find_network(run_dir: Path, case: str | None = None) -> Path:
    candidates = sorted((run_dir / "source").rglob("*.net.xml"))
    if not candidates:
        candidates = sorted(ROOT.rglob("*.net.xml"))
    expected_name = NETWORK_BY_CASE.get(str(case).lower())
    preferred = [path for path in candidates if path.name == expected_name]
    if preferred:
        return preferred[0]
    if not candidates:
        raise FileNotFoundError("no SUMO .net.xml file found")
    return candidates[0]


def parse_shape(value: str) -> list[list[float]]:
    return [[float(part) for part in point.split(",")[:2]]
            for point in value.split()]


def parse_network(path: Path) -> dict:
    root = ET.parse(path).getroot()
    lanes = []
    points = []
    for lane in root.findall(".//lane"):
        shape = lane.get("shape")
        if not shape:
            continue
        coordinates = parse_shape(shape)
        points.extend(coordinates)
        lanes.append({
            "id": lane.get("id"),
            "index": int(lane.get("index", "0")),
            "width": float(lane.get("width", "3.2")),
            "shape": coordinates,
            "internal": (lane.get("id") or "").startswith(":"),
        })
    location = root.find("location")
    if location is not None and location.get("convBoundary"):
        bounds = [float(value) for value in location.get("convBoundary").split(",")]
    elif points:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        bounds = [min(xs), min(ys), max(xs), max(ys)]
    else:
        bounds = [0.0, 0.0, 1.0, 1.0]
    return {"file": path.name, "bounds": bounds, "lanes": lanes}


def find_static_obstacles(run_dir: Path, case: str | None) -> list[dict]:
    """Read scenario obstacles that are intentionally absent from vehicle traces.

    The merge runner models the end of the requesting lane with a stopped SUMO
    vehicle named ``stone``.  Diagnostic vehicle traces only contain controlled
    vehicles, while FCD retains the exact pose of this static object.
    """
    if str(case).lower() not in {"eval6", "eval7"}:
        return []
    candidates = [run_dir / "fcd.xml.gz", run_dir / "fcd.xml"]
    fcd_path = next((path for path in candidates if path.is_file()), None)
    if fcd_path is None:
        return []
    opener = gzip.open if fcd_path.suffix == ".gz" else open
    with opener(fcd_path, "rt", encoding="utf-8") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] != "vehicle":
                continue
            if element.get("id") != "stone":
                element.clear()
                continue
            return [{
                "kind": "obstacle",
                "id": "stone",
                "label": "障害物 stone",
                "x": float(element.get("x", "0")),
                "y": float(element.get("y", "0")),
                "angle_deg": float(element.get("angle", "0")),
                "lane_id": element.get("lane"),
                "lane_position_m": float(element.get("pos", "0")),
                "length_m": 5.0,
                "width_m": 1.8,
                "source": "fcd",
            }]
    return []


def scenario_annotations(run_dir: Path, case: str | None,
                         network: dict) -> list[dict]:
    """Return fixed scenario landmarks drawn independently from traffic state."""
    if str(case).lower() not in {"eval6", "eval7"}:
        return []
    requesting_lane = next(
        (lane for lane in network["lanes"] if lane["id"] == "main_0"), None)
    lane_y = requesting_lane["shape"][0][1] if requesting_lane else -8.0
    lane_width = requesting_lane["width"] if requesting_lane else 3.2
    annotations = [{
        "kind": "merge_zone",
        "label": "合流区間 100 m",
        "start_label": "合流開始 200 m",
        "end_label": "合流完了目安 300 m",
        "start_x": 200.0,
        "end_x": 300.0,
        "y": lane_y,
        "width_m": lane_width,
        "lane_id": "main_0",
    }]
    annotations.extend(find_static_obstacles(run_dir, case))
    return annotations


class ReplayApplication:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir.resolve()
        state_path = find_trace(self.run_dir, "vehicle-states.jsonl", required=True)
        self.frames = FrameStore(state_path)
        self.manifest = json.loads((self.run_dir / "manifest.json").read_text()) \
            if (self.run_dir / "manifest.json").is_file() else {}
        self.replay_stitch = json.loads(
            (self.run_dir / "replay-stitch.json").read_text()) \
            if (self.run_dir / "replay-stitch.json").is_file() else None
        self.events = read_jsonl(find_trace(self.run_dir, "negotiations.jsonl"))
        self.events.sort(key=lambda event: float(event.get("sim_time", 0)))
        self.network = parse_network(find_network(
            self.run_dir, self.manifest.get("case")))
        self.network["annotations"] = scenario_annotations(
            self.run_dir, self.manifest.get("case"), self.network)

    def metadata(self):
        return {
            "run_dir": str(self.run_dir),
            "frame_count": len(self.frames),
            "times": self.frames.times,
            "start_time": self.frames.times[0] if self.frames.times else None,
            "end_time": self.frames.times[-1] if self.frames.times else None,
            "manifest": self.manifest,
            "fcd_available": (self.run_dir / "fcd.xml.gz").is_file(),
            "fcd_complete": self.replay_stitch is None,
            "event_count": len(self.events),
            "scenario_note": (
                "論文上はT字路。引き継ぎ実装は上側流入を使わない十字路ネットワーク。"
                if str(self.manifest.get("case", "")).lower() == "eval3" else None),
        }


def replayable_seed_directories(search_root: Path) -> list[Path]:
    search_root = search_root.resolve()
    if ((search_root / "manifest.json").is_file()
            and find_trace(search_root, "vehicle-states.jsonl") is not None):
        return [search_root]
    directories = []
    for manifest_path in search_root.rglob("manifest.json"):
        if "source" in manifest_path.relative_to(search_root).parts:
            continue
        candidate = manifest_path.parent
        if find_trace(candidate, "vehicle-states.jsonl") is not None:
            directories.append(candidate)
    return sorted(set(directories))


def experiment_root(seed_dir: Path, search_root: Path) -> Path:
    for candidate in [seed_dir, *seed_dir.parents]:
        if candidate == search_root.parent:
            break
        if ((candidate / "experiment-manifest.json").is_file()
                or (candidate / "summary.json").is_file()):
            return candidate
        if candidate == search_root:
            break
    if (seed_dir.name.startswith("seed-")
            and seed_dir.parent.name.lower().startswith("eval")):
        return seed_dir.parent.parent
    return seed_dir


def relative_label(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
        return path.name if relative == Path(".") else relative.as_posix()
    except ValueError:
        return path.name


def format_started_at(manifest: dict) -> str:
    value = manifest.get("started_epoch")
    if value is None:
        return "日時不明"
    return datetime.datetime.fromtimestamp(float(value)).astimezone().strftime("%m/%d %H:%M")


def display_method(experiment_id: str, method: str) -> str:
    normalized_id = experiment_id.lower()
    if "priority-hold-gated" in normalized_id:
        return "条件付き合意保持"
    if "priority-hold-global" in normalized_id:
        return "全交渉合意保持"
    return {
        "deceleration-propagation": "提案手法",
        "thesis-tiv": "山下手法",
    }.get(method, method or "方式不明")


def format_duration(duration) -> str:
    if duration is None:
        return "時間不明"
    value = float(duration)
    return f"{value:g}秒"


def logical_experiment_id(manifest: dict, physical_experiment_id: str) -> str:
    """Group checkpoint recoveries with the batch they resume.

    Recovery runs intentionally live in separate result directories, but they
    are continuations of the same logical experiment from a replay user's
    perspective.  The checkpoint path is persisted in every recovered seed
    manifest, so it is the authoritative link back to the original batch.
    """
    resume_from = (
        manifest.get("checkpointing", {}).get("resume_from")
        if isinstance(manifest.get("checkpointing"), dict) else None
    )
    if resume_from:
        parts = Path(str(resume_from)).parts
        try:
            runs_index = parts.index("runs")
            return parts[runs_index + 1]
        except (ValueError, IndexError):
            pass
    return physical_experiment_id


def physical_experiment_id(root: Path, search_root: Path) -> str:
    """Return the experiment directory name for the modern results/runs layout."""
    if root.parent == search_root / "runs":
        return root.name
    return relative_label(root, search_root)


class ReplayCatalog:
    def __init__(self, search_root: Path):
        self.search_root = search_root.resolve()
        self._entries = []
        self._entry_by_id = {}
        self._applications = {}
        for index, seed_dir in enumerate(
                replayable_seed_directories(self.search_root)):
            manifest = json.loads((seed_dir / "manifest.json").read_text())
            root = experiment_root(seed_dir, self.search_root)
            physical_id = physical_experiment_id(root, self.search_root)
            experiment_id = logical_experiment_id(
                manifest, physical_id)
            selection_id = str(index)
            duration = manifest.get("stop_time") or manifest.get("input_duration")
            method = manifest.get("decision_method") or "方式不明"
            entry = {
                "id": selection_id,
                "experiment_id": experiment_id,
                "physical_experiment_id": physical_id,
                "experiment_label": (
                    f"{format_started_at(manifest)} · "
                    f"{display_method(experiment_id, method)} · "
                    f"{format_duration(duration)}"),
                "case": str(manifest.get("case") or seed_dir.parent.name).lower(),
                "seed": manifest.get("seed", seed_dir.name.removeprefix("seed-")),
                "method": method,
                "duration_s": duration,
                "status": ("completed" if manifest.get("exit_code") == 0 else "unknown"),
                "run_dir": str(seed_dir),
                "started_epoch": manifest.get("started_epoch"),
            }
            self._entries.append(entry)
            self._entry_by_id[selection_id] = entry
        self._entries.sort(key=lambda entry: (
            -(float(entry["started_epoch"] or 0)),
            entry["experiment_id"], entry["case"], str(entry["seed"])))

        # Use one stable label for every case/seed in a logical experiment.
        # Prefer the original batch's manifest over a later recovery manifest.
        grouped_entries = {}
        for entry in self._entries:
            grouped_entries.setdefault(entry["experiment_id"], []).append(entry)
        for experiment_id, entries in grouped_entries.items():
            original = next((entry for entry in entries
                             if entry["physical_experiment_id"] == experiment_id), None)
            representative = original or min(
                entries, key=lambda entry: float(entry["started_epoch"] or 0))
            label = representative["experiment_label"]
            if any(entry["physical_experiment_id"] != experiment_id
                   for entry in entries):
                label += " · 復旧統合"
            for entry in entries:
                entry["experiment_label"] = label

        experiments_by_label = {}
        for entry in reversed(self._entries):
            experiments = experiments_by_label.setdefault(
                entry["experiment_label"], [])
            if entry["experiment_id"] not in experiments:
                experiments.append(entry["experiment_id"])
        for entry in self._entries:
            experiments = experiments_by_label[entry["experiment_label"]]
            if len(experiments) > 1:
                rerun = experiments.index(entry["experiment_id"]) + 1
                entry["experiment_label"] += f" · 再実行{rerun}"
        if not self._entries:
            raise FileNotFoundError(
                f"no replayable manifest and vehicle trace found under {self.search_root}")

    @property
    def default_id(self):
        return self._entries[0]["id"]

    def metadata(self):
        return {"default_id": self.default_id, "entries": self._entries}

    def application(self, selection_id: str | None):
        selection_id = selection_id or self.default_id
        if selection_id not in self._entry_by_id:
            raise KeyError(selection_id)
        if selection_id not in self._applications:
            self._applications[selection_id] = ReplayApplication(
                Path(self._entry_by_id[selection_id]["run_dir"]))
        return self._applications[selection_id]


def make_handler(catalog: ReplayCatalog):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format_, *args):
            return

        def send_json(self, value, status=HTTPStatus.OK):
            payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path == "/api/catalog":
                self.send_json(catalog.metadata())
                return
            try:
                app = catalog.application(query.get("selection", [None])[0])
            except KeyError:
                self.send_json({"error": "unknown replay selection"},
                               HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/meta":
                self.send_json(app.metadata())
                return
            if parsed.path == "/api/network":
                self.send_json(app.network)
                return
            if parsed.path == "/api/events":
                self.send_json(app.events)
                return
            if parsed.path == "/api/frame":
                try:
                    index = int(query.get("index", ["0"])[0])
                    self.send_json(app.frames.get(index))
                except (ValueError, IndexError):
                    self.send_json({"error": "frame index out of range"},
                                   HTTPStatus.BAD_REQUEST)
                return
            relative = "index.html" if parsed.path in ("", "/") else parsed.path.lstrip("/")
            asset = (ASSET_DIR / relative).resolve()
            if ASSET_DIR.resolve() not in asset.parents or not asset.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            payload = asset.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "result_path", type=Path, nargs="?", default=ROOT / "results",
        help="results root or one result's eval*/seed-* directory (default: results)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    catalog = ReplayCatalog(args.result_path)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(catalog))
    url = f"http://{server.server_address[0]}:{server.server_address[1]}/"
    print(json.dumps({"url": url, "search_root": str(catalog.search_root),
                      "replay_count": len(catalog.metadata()["entries"])},
                     ensure_ascii=False), flush=True)
    if not args.no_open:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

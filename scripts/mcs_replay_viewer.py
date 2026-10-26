#!/usr/bin/env python3
"""Serve a local, reusable replay UI for one MCS simulation result."""

from __future__ import annotations

import argparse
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
    for suffix in ("", ".gz"):
        candidate = run_dir / f"{base_name}{suffix}"
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


def find_network(run_dir: Path) -> Path:
    candidates = sorted((run_dir / "source").rglob("*.net.xml"))
    if not candidates:
        candidates = sorted(ROOT.rglob("*.net.xml"))
    preferred = [path for path in candidates if path.name == "junction_three.net.xml"]
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


class ReplayApplication:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir.resolve()
        state_path = find_trace(self.run_dir, "vehicle-states.jsonl", required=True)
        self.frames = FrameStore(state_path)
        self.manifest = json.loads((self.run_dir / "manifest.json").read_text()) \
            if (self.run_dir / "manifest.json").is_file() else {}
        self.events = read_jsonl(find_trace(self.run_dir, "negotiations.jsonl"))
        self.events.sort(key=lambda event: float(event.get("sim_time", 0)))
        self.network = parse_network(find_network(self.run_dir))

    def metadata(self):
        return {
            "run_dir": str(self.run_dir),
            "frame_count": len(self.frames),
            "times": self.frames.times,
            "start_time": self.frames.times[0] if self.frames.times else None,
            "end_time": self.frames.times[-1] if self.frames.times else None,
            "manifest": self.manifest,
            "fcd_available": (self.run_dir / "fcd.xml.gz").is_file(),
            "event_count": len(self.events),
        }


def make_handler(app: ReplayApplication):
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
                query = urllib.parse.parse_qs(parsed.query)
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
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="one result's eval*/seed-* directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    app = ReplayApplication(args.run_dir)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    url = f"http://{server.server_address[0]}:{server.server_address[1]}/"
    print(json.dumps({"url": url, **app.metadata()}, ensure_ascii=False), flush=True)
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

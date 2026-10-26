import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mcs_replay_viewer import FrameStore, parse_network


class ReplayViewerTests(unittest.TestCase):
    def test_frame_store_indexes_uncompressed_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vehicle-states.jsonl"
            records = [
                {"sim_time": 0.1, "vehicles": []},
                {"sim_time": 0.2, "vehicles": [{"vehicle_id": "1"}]},
            ]
            path.write_text("".join(json.dumps(record) + "\n" for record in records))
            store = FrameStore(path)
            self.assertEqual(store.times, [0.1, 0.2])
            self.assertEqual(store.get(1)["vehicles"][0]["vehicle_id"], "1")

    def test_parse_network_returns_lane_shapes_and_bounds(self):
        network = parse_network(ROOT / "junction" / "junction_three.net.xml")
        self.assertEqual(network["bounds"], [0.0, -150.0, 300.0, 150.0])
        self.assertTrue(any(lane["id"] == "bottom_0" for lane in network["lanes"]))
        self.assertTrue(all(len(lane["shape"]) >= 2 for lane in network["lanes"]))


if __name__ == "__main__":
    unittest.main()

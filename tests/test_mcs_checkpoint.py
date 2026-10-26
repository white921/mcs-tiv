import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "func"))
import mcs_checkpoint


class MCSCheckpointTests(unittest.TestCase):
    def test_interval_alignment(self):
        with patch.dict(os.environ, {"MCS_CHECKPOINT_INTERVAL": "60"}):
            self.assertFalse(mcs_checkpoint.is_due(59.9))
            self.assertTrue(mcs_checkpoint.is_due(60.0))
            self.assertTrue(mcs_checkpoint.is_due(120.0))

    def test_save_and_load_paired_state(self):
        with tempfile.TemporaryDirectory() as directory:
            def save_state(path):
                Path(path).write_bytes(b"sumo")

            api = NS(simulation=NS(saveState=Mock(side_effect=save_state)))
            target = mcs_checkpoint.save(
                api, directory, 60.0, {"vehicles": ["1", "2"]},
                {"case": "eval3"})
            manifest, payload, sumo_state = mcs_checkpoint.load(target)
            self.assertEqual(manifest["simulation_time_s"], 60.0)
            self.assertEqual(manifest["case"], "eval3")
            self.assertEqual(payload, {"vehicles": ["1", "2"]})
            self.assertEqual(sumo_state.read_bytes(), b"sumo")

    def test_incomplete_checkpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "checkpoint.json").write_text(json.dumps({
                "schema_version": 1,
                "sumo_state": "sumo.xml.gz",
                "mcs_state": "mcs.pkl",
            }))
            with self.assertRaises(ValueError):
                mcs_checkpoint.load(path)


if __name__ == "__main__":
    unittest.main()

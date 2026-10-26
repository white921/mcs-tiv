import json
import os
import sys
import tempfile
import unittest
from collections import Counter, defaultdict
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

    def test_restore_shared_modules_replaces_mutable_state(self):
        metrics = NS(
            COUNTS=Counter(old=1), GROUPS=defaultdict(Counter),
            VEHICLES={"old": 1}, FOLLOWING_VEHICLES={}, PENDING=["old"],
            PREDICTION=defaultdict(Counter), PREDICTION_EVENTS=["old"],
            PHYSICAL_COLLISION_FRAMES=["old"],
            ACTIVE_PHYSICAL_COLLISIONS={"old"})
        prediction = NS(
            COUNTS=Counter(old=1), RECORDS=["old"],
            ACTIVE_DECISION_UNTIL={"old": 1}, MODE="old")
        tiv = NS(COUNTS=Counter(old=1), EXAMPLES=["old"])
        state = {
            "evaluation_metrics": {
                "COUNTS": Counter(new=2),
                "GROUPS": {"new": Counter(hit=1)},
                "VEHICLES": {"new": 2},
                "FOLLOWING_VEHICLES": {"new": 3},
                "PENDING": ["new"],
                "PREDICTION": {"new": Counter(hit=2)},
                "PREDICTION_EVENTS": ["new"],
                "PHYSICAL_COLLISION_FRAMES": ["collision"],
                "ACTIVE_PHYSICAL_COLLISIONS": {"active"},
            },
            "deceleration_prediction": {
                "COUNTS": Counter(new=2), "RECORDS": ["new"],
                "ACTIVE_DECISION_UNTIL": {"new": 4}, "MODE": "new",
            },
            "thesis_tiv": {
                "COUNTS": Counter(new=2), "EXAMPLES": ["new"],
            },
        }

        mcs_checkpoint.restore_shared_modules(state, metrics, prediction, tiv)

        self.assertEqual(metrics.COUNTS, Counter(new=2))
        self.assertEqual(metrics.PENDING, ["new"])
        self.assertEqual(metrics.PHYSICAL_COLLISION_FRAMES, ["collision"])
        self.assertEqual(metrics.ACTIVE_PHYSICAL_COLLISIONS, {"active"})
        self.assertEqual(prediction.ACTIVE_DECISION_UNTIL, {"new": 4})
        self.assertEqual(prediction.MODE, "new")
        self.assertEqual(tiv.EXAMPLES, ["new"])

    def test_restore_vehicle_controls_reapplies_pending_drive(self):
        api = NS(vehicle=NS(
            getIDList=Mock(return_value=("1",)),
            setLaneChangeMode=Mock(), setSpeedMode=Mock()))
        active = NS(id="1", plannedPath=object(), executionDrive=Mock())
        departed = NS(id="2", plannedPath=object(), executionDrive=Mock())

        mcs_checkpoint.restore_vehicle_controls(api, [active, departed])

        api.vehicle.setLaneChangeMode.assert_called_once_with("1", 0)
        api.vehicle.setSpeedMode.assert_called_once_with("1", 32)
        active.executionDrive.assert_called_once_with()
        departed.executionDrive.assert_not_called()


if __name__ == "__main__":
    unittest.main()

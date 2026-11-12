import ast
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NETWORKS = (ROOT / "threeLane.net.xml", ROOT / "merge" / "threeLane.net.xml")
CONTROLLERS = (ROOT / "func" / "cav_merge2512.py", ROOT / "func" / "cav_merge2512_bus.py")


class MergeTwoLaneModelTests(unittest.TestCase):
    def test_current_merge_networks_have_only_lane_zero_and_one(self):
        for path in NETWORKS:
            root = ET.parse(path).getroot()
            main = root.find("./edge[@id='main']")
            self.assertIsNotNone(main, path)
            lanes = main.findall("lane")
            self.assertEqual([lane.get("id") for lane in lanes], ["main_0", "main_1"], path)
            self.assertEqual([lane.get("index") for lane in lanes], ["0", "1"], path)

            terminal = root.find("./junction[@id='J1']")
            self.assertIsNotNone(terminal, path)
            self.assertEqual(terminal.get("incLanes").split(), ["main_0", "main_1"], path)

    def test_current_merge_controllers_define_two_main_lane_centers(self):
        for path in CONTROLLERS:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            assignments = {}
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id in {"MAIN_LANE_CENTER_LINES", "MERGE_TARGET_CENTER_LINES"}
                    ):
                        assignments[target.id] = ast.literal_eval(node.value)
            self.assertEqual(assignments["MAIN_LANE_CENTER_LINES"], (-8.0, -4.8), path)
            self.assertEqual(assignments["MERGE_TARGET_CENTER_LINES"], (-4.8,), path)

    def test_current_runner_has_no_third_lane_departure_state(self):
        source = (ROOT / "merge" / "merge_agree2512.py").read_text(encoding="utf-8")
        self.assertNotIn("departTime_lane2", source)


if __name__ == "__main__":
    unittest.main()

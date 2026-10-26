import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_CONTROLLERS = tuple(sorted((ROOT / "func").glob("cav_*.py")))


def is_self_attribute(node, name):
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and node.attr == name
    )


class VehicleControlSourceRegressionTests(unittest.TestCase):
    def test_stop_status_is_not_a_discarded_comparison(self):
        offenders = []
        for path in ACTIVE_CONTROLLERS:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Compare):
                    continue
                compare = node.value
                if (
                    is_self_attribute(compare.left, "status")
                    and len(compare.ops) == 1
                    and isinstance(compare.ops[0], ast.Eq)
                    and len(compare.comparators) == 1
                    and isinstance(compare.comparators[0], ast.Constant)
                    and compare.comparators[0].value == "stop"
                ):
                    offenders.append(f"{path.name}:{node.lineno}")

        self.assertEqual(offenders, [])

    def test_route_string_is_not_compared_to_a_list(self):
        offenders = []
        for path in ACTIVE_CONTROLLERS:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                if (
                    is_self_attribute(node.left, "route")
                    and any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops)
                    and any(isinstance(value, (ast.List, ast.Tuple, ast.Set)) for value in node.comparators)
                ):
                    offenders.append(f"{path.name}:{node.lineno}")

        self.assertEqual(offenders, [])

    def test_traci_control_modes_do_not_use_removed_keyword_names(self):
        offenders = []
        for path in ACTIVE_CONTROLLERS:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if keyword.arg in {"lcm", "sm"}:
                        offenders.append(f"{path.name}:{node.lineno}:{keyword.arg}")

        self.assertEqual(offenders, [])

    def test_active_runners_do_not_label_controller_counters_as_collisions(self):
        for relative in (
                "junction/junction_three_agree.py",
                "junction/junction_four_agree.py",
                "merge/merge_agree2512.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn('print("collision :"', source, relative)
            self.assertIn("sumo_physical_collision_episodes", source, relative)


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

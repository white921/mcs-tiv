import hashlib
import os
from pathlib import Path
import random
import runpy
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
sys.path.insert(0, str(ROOT / "scripts"))

from fixed_vehicle_inputs import CASE_SPECS, load_fixed_vehicle_input
from run_thesis_batch import CASES, build_tasks, fixed_input_details


EXPECTED = {
    "eval3": {
        "seeds": (1, 2, 3, 4, 5),
        "counts": {"left": 66, "bottom": 66, "right": 66},
        "total": 198,
        "buses": 50,
    },
    "eval5": {
        "seeds": (1, 2, 3, 4, 5),
        "counts": {"left": 50, "bottom": 50, "right": 50, "top": 50},
        "total": 200,
        "buses": 50,
    },
    "eval7": {
        "seeds": (1, 2, 3, 7, 11),
        "counts": {"requesting": 166, "accepting": 166},
        "total": 332,
        "buses": 83,
    },
}


class FixedVehicleInputTests(unittest.TestCase):
    def paths(self):
        return sorted((ROOT / "fixed_inputs" / "thesis").glob("*/*.jsonl"))

    def test_files_match_batch_cases_and_documented_seeds(self):
        expected_paths = {
            ROOT / "fixed_inputs" / "thesis" / case / f"seed-{seed}.jsonl"
            for case, values in EXPECTED.items()
            for seed in values["seeds"]
        }
        self.assertEqual(set(self.paths()), expected_paths)
        for case, values in EXPECTED.items():
            self.assertEqual(tuple(CASES[case]["seeds"]), values["seeds"])

    def test_every_file_loads_identically_and_preserves_conditions(self):
        for path in self.paths():
            with self.subTest(path=path):
                first = load_fixed_vehicle_input(path)
                second = load_fixed_vehicle_input(path)
                self.assertEqual(first.metadata, second.metadata)
                self.assertEqual(first.events, second.events)

                expected = EXPECTED[first.metadata["case"]]
                batch_case = CASES[first.metadata["case"]]
                self.assertEqual(
                    tuple(first.metadata["flows_vph"].values()),
                    tuple(int(flow) for flow in batch_case["flows"]),
                )
                counts = {
                    approach: sum(event["approach"] == approach for event in first.events)
                    for approach in expected["counts"]
                }
                self.assertEqual(counts, expected["counts"])
                self.assertEqual(len(first.events), expected["total"])
                self.assertEqual(
                    sum(event["vehicle_type"] == "Bus" for event in first.events),
                    expected["buses"],
                )
                self.assertEqual(
                    sum(event["vehicle_type"] == "Car" for event in first.events),
                    expected["total"] - expected["buses"],
                )
                self.assertGreater(first.events[0]["depart_time_s"], 0)
                self.assertLess(first.events[-1]["depart_time_s"], 600)
                spec = CASE_SPECS[first.metadata["case"]]
                for event in first.events:
                    self.assertIn(event["route"], spec["routes"][event["approach"]])

    def test_batch_manifest_metadata_uses_relative_path_schema_and_sha256(self):
        for case, values in EXPECTED.items():
            for seed in values["seeds"]:
                with self.subTest(case=case, seed=seed):
                    details = fixed_input_details(case, seed, 600, "fixed")
                    path = ROOT / details["relative_path"]
                    self.assertFalse(Path(details["relative_path"]).is_absolute())
                    self.assertEqual(details["schema_version"], 1)
                    self.assertEqual(
                        details["sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
                    )
                    self.assertEqual(
                        details["runtime_path"], f"../fixed_inputs/thesis/{case}/seed-{seed}.jsonl"
                    )
                    self.assertEqual(details["prefix_duration_s"], 600.0)
                    self.assertEqual(details["prefix_event_count"], values["total"])
                    self.assertEqual(len(details["prefix_sha256"]), 64)
        prefix_300 = fixed_input_details("eval3", 1, 300, "fixed")
        prefix_40 = fixed_input_details("eval3", 1, 40, "fixed")
        self.assertEqual(prefix_300["prefix_duration_s"], 300.0)
        self.assertEqual(prefix_40["prefix_duration_s"], 40.0)
        self.assertLess(prefix_40["prefix_event_count"], prefix_300["prefix_event_count"])
        with self.assertRaisesRegex(ValueError, r"\(0, 600\]"):
            fixed_input_details("eval3", 1, 601, "fixed")
        self.assertIsNone(fixed_input_details("eval3", 1, 600, "paper-random25"))
        self.assertIsNone(fixed_input_details("eval4", 1, 600, "fixed"))

    def test_platoon_search_inputs_are_valid_and_selectable_by_override(self):
        directories = (
            "eval3-platoon-advance-search",
            "eval3-platoon-search",
            "eval3-platoon-sparse-search",
            "eval3-platoon-timing-search",
        )
        for directory in directories:
            paths = sorted((
                ROOT / "fixed_inputs" / "experiments" / directory
            ).glob("*.jsonl"))
            self.assertEqual(len(paths), 5)
            self._assert_experiment_inputs_are_selectable(paths)

    def _assert_experiment_inputs_are_selectable(self, paths):
        for path in paths:
            with self.subTest(path=path):
                schedule = load_fixed_vehicle_input(
                    path,
                    expected_case="eval3",
                    expected_seed=1,
                    expected_duration_s=600.0,
                    expected_flows_vph={"left": 400, "bottom": 400, "right": 400},
                    expected_bus_share=0.25,
                    prefix_duration_s=300.0,
                )
                self.assertTrue(schedule.events)
                self.assertTrue(all(
                    event["depart_time_s"] < 300 for event in schedule.events))
                relative = path.relative_to(ROOT)
                details = fixed_input_details(
                    "eval3", 1, 300, "fixed",
                    relative_path_override=relative,
                )
                self.assertEqual(details["relative_path"], relative.as_posix())
                self.assertEqual(
                    details["prefix_event_count"], len(schedule.events))

    def test_timing_validation_inputs_cover_five_seeds_per_condition(self):
        for directory in (
            "eval3-platoon-advance-validation",
            "eval3-platoon-timing-validation",
        ):
            root = ROOT / "fixed_inputs" / "experiments" / directory
            condition_directories = sorted(path for path in root.iterdir()
                                           if path.is_dir())
            self.assertEqual(len(condition_directories), 5)
            for condition in condition_directories:
                paths = sorted(condition.glob("seed-*.jsonl"))
                self.assertEqual(len(paths), 5)
                for seed, path in enumerate(paths, 1):
                    schedule = load_fixed_vehicle_input(
                        path, expected_case="eval3", expected_seed=seed,
                        prefix_duration_s=300.0)
                    self.assertTrue(schedule.events)

    def test_prefix_is_stable_and_uses_strictly_earlier_events(self):
        path = ROOT / "fixed_inputs" / "thesis" / "eval3" / "seed-1.jsonl"
        empty = load_fixed_vehicle_input(path, prefix_duration_s=0.1)
        first_step = load_fixed_vehicle_input(path, prefix_duration_s=0.2)
        prefix_a = load_fixed_vehicle_input(path, prefix_duration_s=40)
        prefix_b = load_fixed_vehicle_input(path, prefix_duration_s=40)
        self.assertEqual(empty.events, ())
        self.assertTrue(first_step.events)
        self.assertTrue(all(event["depart_time_s"] < 40 for event in prefix_a.events))
        self.assertEqual(prefix_a.events, prefix_b.events)
        self.assertEqual(prefix_a.prefix_sha256, prefix_b.prefix_sha256)
        with self.assertRaisesRegex(ValueError, r"\(0, 600.0\]"):
            load_fixed_vehicle_input(path, prefix_duration_s=600.1)

    def test_batch_can_select_seed_five_without_changing_defaults(self):
        self.assertEqual(build_tasks(["eval3"], seeds=[5]), [("eval3", 5)])
        self.assertEqual(
            build_tasks(["eval3"], seeds_per_case=2),
            [("eval3", 1), ("eval3", 2)],
        )
        with self.assertRaisesRegex(ValueError, "does not document"):
            build_tasks(["eval7"], seeds=[5])


class FixedScenarioRuntimeTests(unittest.TestCase):
    class FakeSimulation:
        time = 0.0

        @classmethod
        def getTime(cls):
            return cls.time

    class FakeVehicleAPI:
        def __init__(self):
            self.added = []

        def add(self, **kwargs):
            self.added.append(kwargs)

        def setColor(self, *args, **kwargs):
            pass

        def setSpeed(self, *args, **kwargs):
            pass

    @staticmethod
    def module(name, **attributes):
        module = types.ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        return module

    def exercise_runner(self, script, case, seed, inflows, duration):
        fake_vehicle = self.FakeVehicleAPI()
        fake_traci = self.module(
            "traci", simulation=self.FakeSimulation, vehicle=fake_vehicle
        )

        class DummyVehicle:
            def __init__(self, *args, **kwargs):
                pass

        stubs = {
            "numpy": self.module(
                "numpy", isscalar=lambda value: False, mean=lambda values: 0.0
            ),
            "traci": fake_traci,
            "sumolib": self.module("sumolib", checkBinary=lambda name: name),
            "cav_three_junction": self.module("cav_three_junction", CAV=DummyVehicle),
            "cav_three_junction_bus": self.module("cav_three_junction_bus", CAV_bus=DummyVehicle),
            "cav_four_junction": self.module("cav_four_junction", CAV=DummyVehicle),
            "cav_four_junction_bus": self.module("cav_four_junction_bus", CAV_bus=DummyVehicle),
            "cav_merge2512": self.module("cav_merge2512", CAV=DummyVehicle),
            "cav_merge2512_bus": self.module("cav_merge2512_bus", CAV_bus=DummyVehicle),
            "animation_junction": self.module("animation_junction", Animation=object),
            "animation_four_junction": self.module("animation_four_junction", Animation=object),
            "animation_merge": self.module("animation_merge", Animation=object),
            "frenet_merge": self.module("frenet_merge", emergency_stop=lambda *args: None),
        }
        path = ROOT / "fixed_inputs" / "thesis" / case / f"seed-{seed}.jsonl"
        expected = load_fixed_vehicle_input(path, prefix_duration_s=duration)
        with mock.patch.dict(sys.modules, stubs), mock.patch.dict(
            os.environ, {"SUMO_HOME": str(ROOT)}, clear=False
        ):
            namespace = runpy.run_path(str(ROOT / script), run_name=f"fixed_test_{case}")

        namespace["simulation_time"] = float(duration)
        namespace["bus_share"] = 0.25
        namespace["seed"] = str(seed)
        namespace["fixed_input_path"] = str(path)
        namespace["fixed_input_schedule"] = None
        namespace["vehicle_type_rng"] = types.SimpleNamespace(
            seed=mock.Mock(side_effect=AssertionError("runtime vehicle RNG seed")),
            shuffle=mock.Mock(side_effect=AssertionError("runtime vehicle RNG shuffle")),
        )
        for function_name in ("set_environment", "add_vehicle"):
            namespace[function_name].__globals__.update(namespace)

        random_failure = AssertionError("runtime random input call")
        with mock.patch.object(random, "sample", side_effect=random_failure), \
             mock.patch.object(random, "choice", side_effect=random_failure), \
             mock.patch.object(random, "shuffle", side_effect=random_failure), \
             mock.patch.object(random, "seed", side_effect=random_failure):
            with mock.patch("builtins.print"):
                namespace["set_environment"](*inflows)
                runtime_times = sorted({event["depart_time_s"] for event in expected.events})
                for depart_time in runtime_times:
                    self.FakeSimulation.time = depart_time
                    namespace["add_vehicle"]("7")

        added_input_vehicles = len(fake_vehicle.added) - (1 if case == "eval7" else 0)
        self.assertEqual(added_input_vehicles, len(expected.events))

    def test_fixed_paths_run_when_random_input_functions_fail(self):
        cases = (
            ("junction/junction_three_agree.py", "eval3", 1, (400, 400, 400), 40),
            ("junction/junction_four_agree.py", "eval5", 1, (300, 300, 300, 300), 40),
            ("merge/merge_agree2512.py", "eval7", 1, (1000, 1000), 40),
        )
        for script, case, seed, inflows, duration in cases:
            with self.subTest(case=case):
                self.exercise_runner(script, case, seed, inflows, duration)


if __name__ == "__main__":
    unittest.main()

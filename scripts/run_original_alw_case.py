#!/usr/bin/env python3
"""One unchanged archival ALW case, followed by same-seed reference comparison."""
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

RESEARCH = Path("/Users/shige/Documents/重野研/卒論研究")
ARCHIVE = RESEARCH / "資料/山下引き継ぎ原本-2026-02/extracted/引き継ぎ用/sumo-mcs-11"
REFERENCE = RESEARCH / "資料/山下引き継ぎ原本-2026-02/Driveミラー/結果/修論・ITS104/csv/junction/acceptance_three_4.2.3_all400_bus25.csv"
SUMO_HOME = RESEARCH / "再現実験/2026-10-19-paper-original-sumo120/diagnostics/sumo117-package/sumo"
OUTPUT = RESEARCH / "再現実験/2026-10-20-baseline-original"
SIM_PYTHON = "/usr/bin/python3"
KEY = ["2", "1", "400", "400", "400"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_case(path):
    # Native output is a sequence of ragged CSV blocks, not one rectangular table.
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    starts = [i for i, row in enumerate(rows) if row and row[0] == "seed"]
    found = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(rows)
        if rows[start + 1][:5] == KEY:
            found.append((start, rows[start:end]))
    assert len(found) == 1, (str(path), len(found))
    start, block = found[0]
    summary_index = next(i for i, row in enumerate(block) if "0-600" in row)
    column = block[summary_index].index("0-600")
    all_index = next(i for i, row in enumerate(block) if row and row[0] == "All")
    generated = {
        row[0]: dict(zip(block[2][1:7], map(int, row[1:7])))
        for row in block[3:5]
    }
    return block, {
        "path": str(path), "sha256": sha(path),
        "metadata_line": start + 2, "all_speed_line": start + all_index + 1,
        "key": block[1][:5],
        "all_average_speed_m_per_s": float(block[all_index][column]),
        "bus_average_speed_m_per_s": float(block[summary_index + 1][column]),
        "car_average_speed_m_per_s": float(block[summary_index + 2][column]),
        "generated_counts_by_route": generated,
        "negotiation_counters": dict(zip(block[0][5:11], map(int, block[1][5:11]))),
    }


def compare(actual_block, actual, reference_block, reference):
    differences = []
    assert len(actual_block) == len(reference_block)
    for row_index, (actual_row, reference_row) in enumerate(zip(actual_block, reference_block)):
        assert len(actual_row) == len(reference_row), row_index
        for col, (left, right) in enumerate(zip(actual_row, reference_row)):
            if row_index == 1 and col == len(actual_row) - 1:
                continue  # Wall-clock completion date is not a simulation output.
            try:
                equal = float(left) == float(right)
            except ValueError:
                equal = left.strip() == right.strip()
            if not equal:
                differences.append({
                    "block_row": row_index + 1, "column": col + 1,
                    "actual": left, "reference": right,
                })
    delta = actual["all_average_speed_m_per_s"] - reference["all_average_speed_m_per_s"]
    return {
        "actual": actual, "reference": reference,
        "average_speed_difference_m_per_s": delta,
        "average_speed_difference_percent": 100 * delta / reference["all_average_speed_m_per_s"],
        "all_stored_cells_except_date_match": not differences,
        "generated_counts_match": actual["generated_counts_by_route"] == reference["generated_counts_by_route"],
        "negotiation_counters_match": actual["negotiation_counters"] == reference["negotiation_counters"],
        "differing_cells": differences,
    }


def main():
    reference_block, reference = read_case(REFERENCE)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    case = Path(tempfile.mkdtemp(prefix="t3-alw-seed2-", dir=OUTPUT))
    clone = case / "source"
    ignore = shutil.ignore_patterns("statistics", "__pycache__", "*.pyc", ".DS_Store",
                                    ".git", ".mypy_cache", "gif")
    for folder in ("func", "PathPlanning", "junction"):
        shutil.copytree(ARCHIVE / folder, clone / folder, ignore=ignore)
    hashes = {}
    for path in sorted(clone.rglob("*")):
        if path.is_file():
            relative = path.relative_to(clone)
            assert sha(path) == sha(ARCHIVE / relative)
            hashes[str(relative)] = sha(path)
    (clone / "junction/statistics").mkdir()
    env = {key: value for key, value in os.environ.items() if not key.startswith("MCS_")}
    env.update(SUMO_HOME=str(SUMO_HOME), PYTHONPATH=str(SUMO_HOME / "tools"),
               PYTHONDONTWRITEBYTECODE="1", MPLBACKEND="Agg",
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
    versions = json.loads(subprocess.check_output([
        SIM_PYTHON, "-c",
        "import sys,json,numpy,traci,sumolib;"
        "print(json.dumps(dict(python=sys.version,numpy=numpy.__version__,"
        "traci_path=traci.__file__,sumolib_path=sumolib.__file__,"
        "sumo_binary=sumolib.checkBinary('sumo'))))"
    ], text=True, env=env))
    assert versions["python"].startswith("3.9.6 ")
    assert Path(versions["traci_path"]).is_relative_to(SUMO_HOME / "tools")
    assert Path(versions["sumolib_path"]).is_relative_to(SUMO_HOME / "tools")
    assert Path(versions["sumo_binary"]).resolve() == (SUMO_HOME / "bin/sumo").resolve()
    versions["sumo_version"] = subprocess.check_output(
        [versions["sumo_binary"], "--version"], text=True, env=env)
    assert "Version 1.17.0" in versions["sumo_version"]
    command = [SIM_PYTHON, "junction_three_agree.py", "1", "2", "400", "400", "400", "--nogui"]
    manifest = {
        "status": "prepared", "case_directory": str(case), "archive": str(ARCHIVE),
        "method": "ALW", "alpha": 1, "seed": "2", "simulation_seconds": 600,
        "inflows": [400, 400, 400], "bus_probability": 0.25,
        "command": command, "cwd": str(clone / "junction"),
        "started_at": dt.datetime.now().astimezone().isoformat(),
        "versions": versions, "reference": reference,
        "source_hashes": hashes, "source_unchanged_before": True,
        "stdout": "/dev/null; original print calls unchanged",
        "environment": {key: env[key] for key in (
            "SUMO_HOME", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "MPLBACKEND",
            "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")},
        "limitations": [
            "Original author's NumPy version is unconfirmed.",
            "This tests the archived baseline implementation, not proof that every archive setting matches the thesis.",
            "Only one method, condition and seed; not a five-seed paper average."
        ],
        "other_queues_resumed": False,
    }
    dump(case / "manifest.json", manifest)
    print("case_directory=" + str(case), flush=True)
    started = time.monotonic()
    with (case / "runner.err").open("w") as errors:
        process = subprocess.Popen(command, cwd=clone / "junction", env=env,
                                   stdout=subprocess.DEVNULL, stderr=errors)
        manifest.update(status="running", runner_pid=process.pid, supervisor_pid=os.getpid())
        dump(case / "manifest.json", manifest)
        exit_code = process.wait()
    manifest.update(exit_code=exit_code, wall_seconds=time.monotonic() - started,
                    finished_at=dt.datetime.now().astimezone().isoformat(),
                    status="simulation_exited")
    dump(case / "manifest.json", manifest)
    if exit_code:
        manifest["status"] = "failed"
        dump(case / "manifest.json", manifest)
        return exit_code
    try:
        assert all(sha(clone / relative) == value == sha(ARCHIVE / relative)
                   for relative, value in hashes.items())
        assert sha(REFERENCE) == reference["sha256"]
        fcd = clone / "junction/statistics/sumoStat.xml"
        times = []
        parser = ET.iterparse(fcd, events=("start", "end"))
        _, root = next(parser)
        for event, element in parser:
            if event == "end" and element.tag == "timestep":
                times.append(float(element.attrib["time"]))
                root.clear()
        assert times == [round(i / 10, 1) for i in range(6000)]
        actual_block, actual = read_case(clone / "junction/statistics/acceptance_three.csv")
        report = compare(actual_block, actual, reference_block, reference)
        report.update(simulation_seconds=600, timesteps=len(times),
                      source_unchanged_after=True, reference_unchanged=True)
        dump(case / "comparison.json", report)
        manifest.update(status="complete", comparison=str(case / "comparison.json"),
                        source_unchanged_after=True, reference_unchanged=True)
    except Exception as error:
        manifest.update(status="validation_failed", validation_error=repr(error))
        dump(case / "manifest.json", manifest)
        raise
    dump(case / "manifest.json", manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Bounded, serial benchmarks on isolated copies; never launches a full run.

Only the planned-path refresh interval is varied by an in-memory test hook.
All cases retain the same thesis TIV, numerical precision, 600s input schedule,
SUMO version, seed string, and bus draw policy.
"""
import argparse
import atexit
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import signal
import subprocess
import sys
import time

CASES = {
    "t3": ("junction", "junction_three_agree.py", ["400", "400", "400"], []),
    "four5": ("junction", "junction_four_agree.py", ["300"] * 4, ["--bus-share", "0.25"]),
    "merge7": ("merge", "merge_agree2512.py", ["1000", "1000"], ["--bus-share", "0.25"]),
}


def worker(args):
    source = args.output / "source"
    folder, script, flows, extras = CASES[args.case]
    os.chdir(source / folder)
    sys.path.insert(0, str(source / "func"))
    sys.path.insert(0, str(source / "PathPlanning" / "FrenetOptimalTrajectory"))
    import traci
    import thesis_tiv
    # Deliberately confined to this subprocess; does not alter the source files.
    thesis_tiv.planned_update_interval = lambda vehicle, legacy: (
        args.interval if thesis_tiv.enabled(vehicle) else legacy)
    original_step = traci.simulationStep
    state = {"case": args.case, "interval": args.interval, "points": [],
             "finished": False, "last_started_sim_time": 0}
    started = None
    previous = None
    def record():
        if previous is not None:
            state["points"].append({
                "sim_time": previous, "elapsed": time.perf_counter() - started})
    def save():
        (args.output / "timing.json").write_text(json.dumps(state, indent=2))
    def step(*pos, **kw):
        nonlocal started, previous
        if started is None:
            started = time.perf_counter()
        record()  # previous step's complete control/planning work
        result = original_step(*pos, **kw)
        previous = traci.simulation.getTime()
        state["last_started_sim_time"] = previous
        if round(previous * 10) % 50 == 0:
            save()
        return result
    traci.simulationStep = step
    atexit.register(save)
    sys.argv = [script, "7", "2"] + flows + [
        "--nogui", "--quiet", "--duration", "600",
        "--stop-time", str(args.stop_time), "--bus-allocation", "paper-random25"] + extras
    try:
        runpy.run_path(str(source / folder / script), run_name="__main__")
        record()
        state["finished"] = True
    finally:
        save()


def supervise(args):
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=False)
    reports = []
    for interval in args.intervals:
        for case in args.cases:
            out = args.output / (case + "-interval-" + str(interval))
            source = out / "source"
            source.mkdir(parents=True)
            for name in ("func", "PathPlanning", "junction", "merge"):
                shutil.copytree(root / name, source / name, ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "statistics", "gif", "results*", "*.log"))
            for name in ("junction", "merge"):
                (source / name / "statistics").mkdir()
            hashes = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in source.rglob("*") if p.is_file()
                      and p.suffix in (".py", ".xml", ".sumocfg")}
            env = dict(os.environ, SUMO_HOME=str(args.sumo_home),
                       PYTHONPATH=str(args.sumo_home / "tools"), MPLBACKEND="Agg",
                       OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                       MCS_TIV_IMPLEMENTATION="thesis", MCS_TIV_AUDIT=str(out / "tiv-audit.json"))
            cmd = [sys.executable, str(Path(__file__).resolve()), "--worker",
                   "--case", case, "--interval", str(interval), "--output", str(out),
                   "--stop-time", str(args.stop_time)]
            report = {"case": case, "interval": interval, "input_duration": 600,
                      "target_sim_time": args.stop_time, "wall_cap": args.wall_cap,
                      "source_sha256": hashes, "command": cmd}
            (out / "manifest.json").write_text(json.dumps(report, indent=2))
            print("START", case, interval, flush=True)
            started = time.perf_counter()
            with (out / "stdout.log").open("w") as stdout, (out / "stderr.log").open("w") as stderr:
                process = subprocess.Popen(cmd, env=env, stdout=stdout, stderr=stderr,
                                           start_new_session=True)
                try:
                    process.wait(timeout=args.wall_cap)
                    report["wall_cap_reached"] = False
                except subprocess.TimeoutExpired:
                    report["wall_cap_reached"] = True
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=5)
                finally:
                    # The process group belongs solely to this test (including SUMO).
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            report["wall_seconds"] = time.perf_counter() - started
            report["exit_code"] = process.returncode
            timing_file = out / "timing.json"
            if timing_file.exists():
                timing = json.loads(timing_file.read_text())
                points = timing["points"]
                report["finished"] = timing["finished"]
                report["last_complete_step"] = points[-1] if points else None
                report["checkpoints"] = {
                    str(t): next((p["elapsed"] for p in points
                                  if abs(p["sim_time"] - t) < 1e-5), None)
                    for t in (10, 20, 30, 40, 60)}
            tiv_file = out / "tiv-audit.json"
            if tiv_file.exists():
                report["tiv_counts"] = json.loads(tiv_file.read_text())["counts"]
            report["source_unchanged"] = all(
                hashlib.sha256((source / path).read_bytes()).hexdigest() == value
                for path, value in hashes.items())
            (out / "manifest.json").write_text(json.dumps(report, indent=2))
            reports.append({k: v for k, v in report.items() if k != "source_sha256"})
            (args.output / "summary.json").write_text(json.dumps(reports, indent=2))
            print("DONE", json.dumps(reports[-1]), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sumo-home", type=Path)
    parser.add_argument("--stop-time", type=float, default=40)
    parser.add_argument("--wall-cap", type=float, default=180)
    parser.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    parser.add_argument("--intervals", nargs="+", type=float, default=[.1, 1.0])
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case", choices=list(CASES))
    parser.add_argument("--interval", type=float)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker:
        worker(args)
    else:
        if args.sumo_home is None:
            parser.error("--sumo-home is required")
        args.sumo_home = args.sumo_home.resolve()
        supervise(args)

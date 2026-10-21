"""Isolated ONE-case run, never appends to the workspace's historical CSV."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from audit_thesis_run import audit_run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sumo-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-time", type=float)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    source = destination / "source"
    source.mkdir()
    for name in ("func", "PathPlanning", "junction"):
        shutil.copytree(root / name, source / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "statistics", "results*", "*.log"))
    (source / "junction" / "statistics").mkdir()
    env = dict(os.environ, SUMO_HOME=str(args.sumo_home.resolve()),
               PYTHONPATH=str(args.sumo_home.resolve() / "tools"),
               MPLBACKEND="Agg", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MCS_TIV_IMPLEMENTATION="thesis", MCS_TIV_AUDIT=str(destination / "tiv-audit.json"))
    command = [sys.executable, "-u", "junction_three_agree.py", "7", "2",
               "400", "400", "400", "--nogui", "--quiet", "--duration", "600",
               "--bus-allocation", "paper-random25"]
    if args.stop_time:
        command += ["--stop-time", str(args.stop_time)]
    def hashes():
        return {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in source.rglob("*") if p.is_file()
                and "statistics" not in p.parts and p.suffix in (".py", ".xml", ".sumocfg")}
    initial_hashes = hashes()
    started = time.time()
    version = subprocess.check_output([str(args.sumo_home / "bin" / "sumo"), "--version"], text=True)
    dependencies = subprocess.check_output([sys.executable, "-c",
        "import sys,numpy,matplotlib,traci,sumolib; "
        "print(sys.version); print('numpy',numpy.__version__); "
        "print('matplotlib',matplotlib.__version__); "
        "print('traci',traci.__file__); print('sumolib',sumolib.__file__)"], env=env, text=True)
    manifest = {"case": "Eval.3-1 / TIVtep / seed2", "command": command,
                "input_duration": 600, "stop_time": args.stop_time or 600,
                "sumo_version": version, "dependencies": dependencies,
                "source_sha256": initial_hashes, "started_epoch": started,
                "paper_mean_five_seeds_mps": 7.4159,
                "note": "Single seed is not directly comparable to the published five-seed mean."}
    paper = Path("/Users/shige/Zotero/storage/AZI3LZFF/master_thesis_yamashita_yutaro_final.pdf")
    manifest["paper"] = {"path": str(paper),
                         "sha256": hashlib.sha256(paper.read_bytes()).hexdigest()}
    shutil.copy2(root / "docs" / "thesis-audit.md", destination / "implementation-assumptions.md")
    manifest["assumptions_sha256"] = hashlib.sha256(
        (destination / "implementation-assumptions.md").read_bytes()).hexdigest()
    def save():
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    save()
    with (destination / "stdout.log").open("w") as stdout, (destination / "stderr.log").open("w") as stderr:
        process = subprocess.Popen(command, cwd=source / "junction", env=env,
                                   stdout=stdout, stderr=stderr)
        manifest["pid"] = process.pid
        save()
        print(json.dumps({"pid": process.pid, "output": str(destination)}), flush=True)
        result = process.wait()
    manifest.update(exit_code=result, elapsed_seconds=time.time() - started,
                    source_unchanged=(initial_hashes == hashes()))
    try:
        audit = json.loads((destination / "tiv-audit.json").read_text())
        manifest["tiv_counts"] = audit["counts"]
        manifest["audit_valid"] = True
    except (OSError, ValueError) as error:
        manifest["audit_valid"] = False
        manifest["audit_error"] = str(error)
        if result == 0:
            result = 2
    manifest["verified_exit_code"] = result
    save()
    if result == 0:
        checked = audit_run(destination)
        (destination / "result-audit.json").write_text(
            json.dumps(checked, indent=2, allow_nan=False))
    print(json.dumps({k: manifest[k] for k in ("exit_code", "elapsed_seconds", "source_unchanged")}), flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

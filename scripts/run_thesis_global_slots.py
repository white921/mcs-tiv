#!/usr/bin/env python3
"""Run one thesis batch while filling machine-wide SUMO slots dynamically.

The normal thesis runner still owns the experiment directory, manifests, logs,
source audit, and task execution.  This wrapper only replaces its executor so
queued tasks wait until the machine-wide limit has capacity.  Reservations are
counted before SUMO starts, preventing a launch race while an existing batch is
finishing on the same host.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
EVENT_LOCK = threading.Lock()


def available_slots(*, total_sumo, owned_sumo, reserved_runs, limit):
    """Return launch capacity after separating this wrapper's SUMO processes."""
    external_sumo = max(0, total_sumo - owned_sumo)
    return max(0, limit - external_sumo - reserved_runs)


def sumo_processes(output):
    """Return ``(total, owned)`` SUMO counts using the output path as owner ID."""
    result = subprocess.run(
        ["pgrep", "-x", "sumo"], text=True, capture_output=True, check=False)
    if result.returncode == 1:
        return 0, 0
    if result.returncode != 0:
        raise RuntimeError(f"pgrep failed: {result.stderr.strip()}")
    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    owner = str(output.resolve())
    owned = 0
    for pid in pids:
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
        except FileNotFoundError:
            continue
        if owner.encode() in command:
            owned += 1
    return len(pids), owned


def append_event(output, event, **fields):
    if not output.is_dir():
        return
    record = {
        "time": datetime.datetime.now().astimezone().isoformat(),
        "event": event,
        **fields,
    }
    with EVENT_LOCK:
        with (output / "global-slot-orchestration.jsonl").open(
                "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, allow_nan=False) + "\n")


class GlobalSlotExecutor(concurrent.futures.ThreadPoolExecutor):
    """Thread executor whose submitted simulations reserve global SUMO slots."""

    def __init__(self, *args, machine_limit, output, poll_seconds=1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.machine_limit = machine_limit
        self.output = output
        self.poll_seconds = poll_seconds
        self._reservation = threading.Condition()
        self._reserved_runs = 0
        self._max_machine_sumo = 0
        self._violation = None

    def _reserve(self):
        with self._reservation:
            while True:
                total, owned = sumo_processes(self.output)
                self._max_machine_sumo = max(self._max_machine_sumo, total)
                if total > self.machine_limit:
                    self._violation = (
                        f"machine-wide SUMO count {total} exceeded "
                        f"{self.machine_limit}")
                    raise RuntimeError(self._violation)
                capacity = available_slots(
                    total_sumo=total,
                    owned_sumo=owned,
                    reserved_runs=self._reserved_runs,
                    limit=self.machine_limit,
                )
                if capacity:
                    self._reserved_runs += 1
                    append_event(
                        self.output, "slot_reserved",
                        total_sumo=total, owned_sumo=owned,
                        reserved_runs=self._reserved_runs,
                        machine_limit=self.machine_limit,
                    )
                    return
                self._reservation.wait(self.poll_seconds)

    def _release(self):
        with self._reservation:
            self._reserved_runs -= 1
            total, owned = sumo_processes(self.output)
            self._max_machine_sumo = max(self._max_machine_sumo, total)
            append_event(
                self.output, "slot_released",
                total_sumo=total, owned_sumo=owned,
                reserved_runs=self._reserved_runs,
                machine_limit=self.machine_limit,
            )
            self._reservation.notify_all()

    def submit(self, fn, /, *args, **kwargs):
        def guarded():
            self._reserve()
            try:
                return fn(*args, **kwargs)
            finally:
                self._release()

        return super().submit(guarded)

    def shutdown(self, wait=True, *, cancel_futures=False):
        super().shutdown(wait=wait, cancel_futures=cancel_futures)
        append_event(
            self.output, "global_slot_executor_finished",
            max_machine_sumo_processes=self._max_machine_sumo,
            machine_slot_violation=self._violation,
            machine_limit=self.machine_limit,
        )


def load_runner():
    path = ROOT / "scripts" / "run_thesis_batch.py"
    spec = importlib.util.spec_from_file_location("run_thesis_batch_global", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--machine-slots", type=int, default=15)
    wrapper, runner_argv = parser.parse_known_args()
    if wrapper.machine_slots < 1:
        parser.error("--machine-slots must be positive")
    try:
        output_index = runner_argv.index("--output") + 1
        output = Path(runner_argv[output_index]).resolve()
    except (ValueError, IndexError):
        parser.error("the wrapped runner requires an explicit --output")

    runner = load_runner()
    original_executor = runner.concurrent.futures.ThreadPoolExecutor
    executor_holder = {}

    def executor_factory(*args, **kwargs):
        executor = GlobalSlotExecutor(
            *args, machine_limit=wrapper.machine_slots, output=output, **kwargs)
        executor_holder["executor"] = executor
        append_event(output, "global_slot_wrapper_started",
                     machine_limit=wrapper.machine_slots)
        return executor

    runner.concurrent.futures.ThreadPoolExecutor = executor_factory
    previous_argv = sys.argv
    sys.argv = [str(ROOT / "scripts" / "run_thesis_batch.py"), *runner_argv]
    try:
        result = runner.main()
        executor = executor_holder["executor"]
        manifest_path = output / "experiment-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["scheduler"] = {
            "type": "machine-wide-work-conserving-slots",
            "machine_slot_limit": wrapper.machine_slots,
            "max_machine_sumo_processes": executor._max_machine_sumo,
            "machine_slot_violation": executor._violation,
            "orchestration_log": "global-slot-orchestration.jsonl",
        }
        runner.write_json(manifest_path, manifest)
        append_event(
            output, "global_slot_wrapper_finished",
            max_machine_sumo_processes=executor._max_machine_sumo,
            machine_slot_violation=executor._violation,
            machine_limit=wrapper.machine_slots,
        )
        return result
    finally:
        sys.argv = previous_argv
        runner.concurrent.futures.ThreadPoolExecutor = original_executor


if __name__ == "__main__":
    raise SystemExit(main())

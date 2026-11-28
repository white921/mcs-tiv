#!/usr/bin/env python3
"""Audit, summarize, compress, and save one completed Eval.3/5 result set."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET


LAMBDA = 0.525
FORMULA = "M=(1-lambda)*Z_time+lambda*Z_follow; accept iff M<=0"
SEEDS = tuple(range(13, 23))
COMPACT_TOP_LEVEL_FILES = (
    "experiment-manifest.json",
    "summary.json",
    "eval35-comparison-summary.json",
    "post-run-audit.json",
    "compression-audit.json",
    "storage-split-audit.json",
    "retention-audit.json",
    "runner.log",
    "orchestration.jsonl",
)
COMPACT_RUN_FILES = (
    "manifest.json",
    "evaluation-metrics.json",
    "tiv-audit.json",
    "deceleration-audit.json",
    "physical-collisions.jsonl",
    "stdout.log",
    "stderr.log",
)
RAW_ARTIFACT_NAMES = {
    "runtime.jsonl",
    "runtime.jsonl.gz",
    "fcd.xml.gz",
    "negotiations.jsonl",
    "negotiations.jsonl.gz",
    "conflicts.jsonl",
    "conflicts.jsonl.gz",
    "vehicle-states.jsonl",
    "vehicle-states.jsonl.gz",
    "prediction-events.jsonl",
    "prediction-events.jsonl.gz",
    "mcs-state.pkl",
    "mcs-state.pkl.xz",
    "sumo-state.xml.gz",
}
FATAL_PATTERN = re.compile(
    r"traceback|segmentation fault|fatal error|connection closed by sumo|"
    r"process exited with code [1-9]|\berror:\s",
    re.IGNORECASE,
)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
    return hasher.hexdigest()


def last_runtime_time(path):
    last = None
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                last = json.loads(line)
    if last is None:
        raise RuntimeError(f"empty runtime log: {path}")
    for key in ("simulation_time_s", "simulation_time", "sim_time_s", "sim_time", "time_s"):
        if key in last:
            return float(last[key])
    raise RuntimeError(f"runtime record lacks simulation time: {path}")


def fcd_end_time(path):
    last = None
    with gzip.open(path, "rb") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag == "timestep":
                last = float(element.attrib["time"])
            element.clear()
    return last


def group_total(metrics, field):
    return sum(float(metrics.get("groups", {}).get(group, {}).get(field, 0.0))
               for group in ("car", "bus"))


def flows_match(manifest_flows, case, expected_flows):
    expected = list(expected_flows)
    if case == "eval7":
        return manifest_flows == {
            "requesting": expected[0],
            "accepting": expected[1],
        }
    return manifest_flows == expected


def analyze_run(context, seed, source_commit):
    spec = context["spec"]
    run = context["output"] / spec["case"] / f"seed-{seed}"
    required = (
        "manifest.json", "evaluation-metrics.json", "tiv-audit.json",
        "physical-collisions.jsonl", "stdout.log", "stderr.log",
        "runtime.jsonl", "fcd.xml.gz", "negotiations.jsonl",
        "conflicts.jsonl", "vehicle-states.jsonl", "prediction-events.jsonl",
    )
    if spec["method"] == "proposal":
        required += ("deceleration-audit.json",)
    missing = [name for name in required if not (run / name).is_file()]
    if missing:
        raise RuntimeError(f"{run}: missing {missing}")
    manifest = json.loads((run / "manifest.json").read_text())
    metrics = json.loads((run / "evaluation-metrics.json").read_text())
    fixed = manifest["fixed_vehicle_input"]
    fixed_path = context["root"] / fixed["path"]
    stderr = (run / "stderr.log").read_text(errors="replace")
    stdout = (run / "stdout.log").read_text(errors="replace")
    checkpoints = sorted((run / "checkpoints").glob("t*/checkpoint.json"))
    checkpoint_times = []
    checkpoint_errors = []
    for checkpoint_path in checkpoints:
        checkpoint = json.loads(checkpoint_path.read_text())
        checkpoint_times.append(float(checkpoint.get("simulation_time_s", -1)))
        directory = checkpoint_path.parent
        for name in (checkpoint.get("mcs_state"), checkpoint.get("sumo_state")):
            if not name or not (directory / str(name)).is_file():
                checkpoint_errors.append(f"{directory.name}: {name} missing")
    proposal = spec["method"] == "proposal"
    prediction = manifest.get("deceleration_prediction")
    checks = {
        "exit_code": manifest.get("exit_code") == 0,
        "source_unchanged": manifest.get("source_unchanged") is True,
        "source_commit": manifest.get("git", {}).get("commit") == source_commit,
        "git_clean": manifest.get("git", {}).get("dirty") is False,
        "case": manifest.get("case") == spec["case"],
        "seed": manifest.get("seed") == seed,
        "flows": flows_match(
            manifest.get("flows_vph"), spec["case"], spec["flows"]
        ),
        "duration": manifest.get("input_duration") == 600.0,
        "bus_share": math.isclose(float(manifest.get("bus_share", -1)), 0.25),
        "bus_fixed": manifest.get("bus_allocation") == "fixed",
        "method": manifest.get("decision_method") == (
            "normalized-deceleration-propagation" if proposal else "tivtep"),
        "lambda": (
            prediction is not None
            and prediction.get("decision_formula") == FORMULA
            and math.isclose(float(prediction.get("convex_lambda", -1)), LAMBDA)
        ) if proposal else prediction is None,
        "fixed_input_exists": fixed_path.is_file(),
        "fixed_input_sha256": fixed_path.is_file() and sha256(fixed_path) == fixed.get("sha256"),
        "python": str(manifest.get("python_version", "")).startswith("3.15.1"),
        "sumo": "1.28.0" in str(manifest.get("sumo_version", "")).splitlines()[0],
        "diagnostic_traces": manifest.get("diagnostic_traces_enabled") is True,
        "checkpoints": (
            len(checkpoints) == 10
            and checkpoint_times == [float(value) for value in range(60, 601, 60)]
            and not checkpoint_errors
        ),
        "fcd_end": math.isclose(float(fcd_end_time(run / "fcd.xml.gz")), 599.9, abs_tol=0.011),
        "runtime_end": math.isclose(last_runtime_time(run / "runtime.jsonl"), 600.0, abs_tol=0.011),
        "collision_free": metrics["physical_safety"]["unique_collision_episodes"] == 0,
        "collision_log_empty": (run / "physical-collisions.jsonl").stat().st_size == 0,
        "fatal_logs": FATAL_PATTERN.search(stderr + "\n" + stdout) is None,
    }
    errors = [name for name, passed in checks.items() if not passed] + checkpoint_errors
    return {
        "context": context["tag"],
        "condition": spec["condition"],
        "method": spec["method"],
        "seed": seed,
        "all_speed_mps": float(manifest["all_speed_mps"]),
        "car_speed_mps": float(metrics["groups"]["car"]["mean_speed_mps"]),
        "bus_speed_mps": float(metrics["groups"]["bus"]["mean_speed_mps"]),
        "stop_time_s": group_total(metrics, "stop_time_s"),
        "hard_brake_time_s": group_total(metrics, "hard_brake_time_s"),
        "physical_collision_episodes": metrics["physical_safety"]["unique_collision_episodes"],
        "fixed_input_sha256": fixed["sha256"],
        "checks": checks,
        "errors": errors,
    }


def bootstrap_interval(values, seed, draws=200_000):
    rng = random.Random(seed)
    n = len(values)
    samples = []
    for _ in range(draws):
        samples.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    samples.sort()
    return [samples[int(draws * 0.025)], samples[int(draws * 0.975)]]


def aggregate(rows):
    return {
        "seed_count": len(rows),
        "all_speed_mean_mps": statistics.mean(row["all_speed_mps"] for row in rows),
        "all_speed_sample_sd_mps": statistics.stdev(row["all_speed_mps"] for row in rows),
        "car_speed_mean_mps": statistics.mean(row["car_speed_mps"] for row in rows),
        "bus_speed_mean_mps": statistics.mean(row["bus_speed_mps"] for row in rows),
        "stop_time_mean_s": statistics.mean(row["stop_time_s"] for row in rows),
        "hard_brake_time_mean_s": statistics.mean(row["hard_brake_time_s"] for row in rows),
        "physical_collision_episodes": sum(row["physical_collision_episodes"] for row in rows),
    }


def compare_condition(condition, rows):
    yamashita = {row["seed"]: row for row in rows
                 if row["condition"] == condition and row["method"] == "yamashita"}
    proposal = {row["seed"]: row for row in rows
                if row["condition"] == condition and row["method"] == "proposal"}
    if set(yamashita) != set(SEEDS) or set(proposal) != set(SEEDS):
        raise RuntimeError(f"{condition}: incomplete paired seeds")
    pairs = []
    for seed in SEEDS:
        difference = proposal[seed]["all_speed_mps"] - yamashita[seed]["all_speed_mps"]
        pairs.append({
            "seed": seed,
            "yamashita_speed_mps": yamashita[seed]["all_speed_mps"],
            "proposal_speed_mps": proposal[seed]["all_speed_mps"],
            "difference_mps": difference,
            "improvement_percent": difference / yamashita[seed]["all_speed_mps"] * 100,
        })
    differences = [pair["difference_mps"] for pair in pairs]
    yam_rows = [yamashita[seed] for seed in SEEDS]
    proposal_rows = [proposal[seed] for seed in SEEDS]
    yam_mean = statistics.mean(row["all_speed_mps"] for row in yam_rows)
    proposal_mean = statistics.mean(row["all_speed_mps"] for row in proposal_rows)
    return {
        "condition": condition,
        "yamashita": aggregate(yam_rows),
        "proposal": aggregate(proposal_rows),
        "paired": pairs,
        "speed_difference_mean_mps": statistics.mean(differences),
        "speed_improvement_from_means_percent": (proposal_mean / yam_mean - 1) * 100,
        "proposal_faster_seed_count": sum(value > 0 for value in differences),
        "paired_bootstrap_95_percent_mps": bootstrap_interval(
            differences, seed=f"eval35-lambda0525:{condition}"
        ),
    }


def remove_source_snapshots(output):
    removed = []
    for source in sorted(output.glob("eval*/seed-*/source")):
        if source.parent.parent.parent != output:
            raise RuntimeError(f"refusing to remove unexpected source path: {source}")
        shutil.rmtree(source)
        removed.append(str(source.relative_to(output)))
    return removed


def git_save(context, push):
    root = context["root"]
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    if branch != context["branch"]:
        raise RuntimeError(f"{context['tag']}: expected branch {context['branch']}, got {branch}")
    relative = context["output"].relative_to(root)
    subprocess.run(["git", "add", "-f", "--", str(relative)], cwd=root, check=True)
    staged = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"], cwd=root, text=True
    ).splitlines()
    if not staged or any(not path.startswith(str(relative) + "/") for path in staged):
        raise RuntimeError(f"{context['tag']}: unexpected staged files: {staged[:5]}")
    subprocess.run(
        ["git", "commit", "-m", f"results: add {context['tag']} formal runs"],
        cwd=root, check=True,
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if push:
        subprocess.run(["git", "push", "origin", f"HEAD:{context['branch']}"], cwd=root, check=True)
    return commit


def compact_files(context):
    """Return the compact formal evidence that may be committed."""
    output = context["output"]
    selected = {output / name for name in COMPACT_TOP_LEVEL_FILES}
    for seed in SEEDS:
        run = output / context["spec"]["case"] / f"seed-{seed}"
        selected.update(run / name for name in COMPACT_RUN_FILES if (run / name).is_file())
        selected.update(sorted((run / "checkpoints").glob("t*/checkpoint.json")))
    missing = sorted(str(path) for path in selected if not path.is_file())
    if missing:
        raise RuntimeError(f"{context['tag']}: missing compact evidence: {missing[:5]}")
    forbidden = sorted(
        str(path.relative_to(output))
        for path in selected
        if path.name in RAW_ARTIFACT_NAMES or "source" in path.relative_to(output).parts
    )
    if forbidden:
        raise RuntimeError(f"{context['tag']}: raw artifact selected: {forbidden[:5]}")
    return selected


def audit_existing_finalization(context, source_commit):
    """Validate a completed pre-policy finalization without touching its raw files."""
    output = context["output"]
    report = json.loads((output / "eval35-comparison-summary.json").read_text())
    post_run = json.loads((output / "post-run-audit.json").read_text())
    compression = json.loads((output / "compression-audit.json").read_text())
    split = json.loads((output / "storage-split-audit.json").read_text())
    checks = {
        "report_source_commit": report.get("source_commit") == source_commit,
        "report_eval": report.get("eval") == context["spec"]["eval"],
        "report_run_count": report.get("run_count") == 2 * len(SEEDS),
        "report_pre_compression_audit": report.get("all_pre_compression_checks_passed") is True,
        "report_rows": (
            len(report.get("per_run", [])) == 2 * len(SEEDS)
            and all(not row.get("errors") for row in report.get("per_run", []))
        ),
        "post_run_audit": (
            post_run.get("ok") is True
            and post_run.get("phase") == "complete"
            and post_run.get("source_commit") == source_commit
        ),
        "compression_audit": (
            compression.get("all_verified") is True
            and compression.get("run_count") == len(SEEDS)
            and compression.get("item_count") == 13 * len(SEEDS)
        ),
        "storage_split_audit": split.get("all_verified") is True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"{context['tag']}: existing finalization audit failed: {failed}")

    raw_files = [
        path for path in output.rglob("*")
        if path.is_file() and path.name in RAW_ARTIFACT_NAMES
    ]
    source_snapshots = [path for path in output.glob("eval*/seed-*/source") if path.exists()]
    retention = {
        "schema_version": 1,
        "classification": "formal",
        "policy": "compact-git-evidence-with-raw-outside-repository",
        "source_commit": source_commit,
        "compact_git_evidence": [
            "experiment and run manifests",
            "evaluation and method audit metrics",
            "comparison summary and finalization audits",
            "checkpoint metadata and compact logs",
        ],
        "excluded_raw_artifact_count": len(raw_files),
        "excluded_raw_artifact_bytes": sum(path.stat().st_size for path in raw_files),
        "raw_artifact_location": str(output),
        "external_storage": "pending",
        "source_snapshots_present": [str(path.relative_to(output)) for path in source_snapshots],
        "compression_round_trip_verified": True,
        "storage_split_verified": True,
        "ok": not source_snapshots,
    }
    if source_snapshots:
        raise RuntimeError(f"{context['tag']}: source snapshots remain after verification")
    write_json(output / "retention-audit.json", retention)
    return retention


def git_save_compact(context, push):
    """Commit only compact evidence while retaining raw artifacts in the worktree."""
    root = context["root"]
    output = context["output"]
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    if branch != context["branch"]:
        raise RuntimeError(f"{context['tag']}: expected branch {context['branch']}, got {branch}")

    selected = compact_files(context)
    staged_before = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"], cwd=root, text=True
    ).splitlines()
    output_relative = output.relative_to(root)
    outside = [path for path in staged_before if not path.startswith(str(output_relative) + "/")]
    if outside:
        raise RuntimeError(f"{context['tag']}: unrelated staged files: {outside[:5]}")
    if staged_before:
        subprocess.run(
            ["git", "restore", "--staged", "--", *staged_before], cwd=root, check=True
        )

    relative_selected = sorted(str(path.relative_to(root)) for path in selected)
    subprocess.run(["git", "add", "-f", "--", *relative_selected], cwd=root, check=True)
    staged = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"], cwd=root, text=True
    ).splitlines()
    if set(staged) != set(relative_selected):
        raise RuntimeError(f"{context['tag']}: compact staging mismatch")
    staged_raw = [path for path in staged if Path(path).name in RAW_ARTIFACT_NAMES]
    if staged_raw:
        raise RuntimeError(f"{context['tag']}: raw artifacts staged: {staged_raw[:5]}")

    subprocess.run(
        ["git", "commit", "-m", f"results: add compact {context['tag']} formal evidence"],
        cwd=root, check=True,
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if push:
        subprocess.run(["git", "push", "origin", f"HEAD:{context['branch']}"], cwd=root, check=True)
    return commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval", choices=("eval3", "eval5"), required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--context", action="append", nargs=4, required=True,
        metavar=("TAG", "ROOT", "RUN_NAME", "RESULT_BRANCH"),
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--push", action="store_true")
    parser.add_argument(
        "--save-existing-compact",
        action="store_true",
        help="save already verified outputs as compact Git evidence without touching raw artifacts",
    )
    args = parser.parse_args()

    script_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(script_root / "scripts"))
    from compress_diagnostic_artifacts import process as compress  # noqa: E402

    contexts = []
    for tag, root_text, run_name, branch in args.context:
        root = Path(root_text).resolve()
        output = root / "results" / "runs" / run_name
        experiment = json.loads((output / "experiment-manifest.json").read_text())
        if experiment.get("status") != "completed":
            raise RuntimeError(f"{tag}: experiment is not completed")
        if experiment.get("completed_simulations") != len(SEEDS):
            raise RuntimeError(f"{tag}: completed count mismatch")
        context = {
            "tag": tag, "root": root, "output": output, "branch": branch,
            "spec": {
                "eval": experiment["eval"], "condition": experiment["condition"],
                "case": experiment["case"], "flows": tuple(experiment["flows_vph"]),
                "method": "proposal" if experiment["deceleration_convex_lambda"] is not None else "yamashita",
            },
        }
        if context["spec"]["eval"] != args.eval:
            raise RuntimeError(f"{tag}: expected {args.eval}")
        contexts.append(context)

    if args.save_existing_compact:
        commits = {}
        for context in contexts:
            audit_existing_finalization(context, args.source_commit)
            commits[context["tag"]] = git_save_compact(context, args.push)
        print(json.dumps({"eval": args.eval, "status": "completed", "commits": commits}))
        return 0

    rows = [
        analyze_run(context, seed, args.source_commit)
        for context in contexts for seed in SEEDS
    ]
    errors = [f"{row['context']}/seed-{row['seed']}: {row['errors']}"
              for row in rows if row["errors"]]
    if errors:
        raise RuntimeError("pre-compression audit failed:\n" + "\n".join(errors))

    conditions = sorted({row["condition"] for row in rows})
    comparisons = [compare_condition(condition, rows) for condition in conditions]
    report = {
        "schema_version": 1,
        "eval": args.eval,
        "classification": "formal",
        "source_commit": args.source_commit,
        "lambda": LAMBDA,
        "seeds": list(SEEDS),
        "run_count": len(rows),
        "all_pre_compression_checks_passed": True,
        "per_run": rows,
        "comparisons": comparisons,
    }
    for context in contexts:
        write_json(context["output"] / "eval35-comparison-summary.json", report)
        write_json(context["output"] / "post-run-audit.json", {
            "schema_version": 1,
            "ok": True,
            "phase": "pre-compression",
            "source_commit": args.source_commit,
            "run_count": len(SEEDS),
            "errors": [],
        })

    for context in contexts:
        compress(context["output"], args.workers)
        removed = remove_source_snapshots(context["output"])
        compression = json.loads((context["output"] / "compression-audit.json").read_text())
        split = json.loads((context["output"] / "storage-split-audit.json").read_text())
        audit = {
            "schema_version": 1,
            "ok": compression.get("all_verified") is True and split.get("all_verified") is True,
            "phase": "complete",
            "source_commit": args.source_commit,
            "run_count": len(SEEDS),
            "compression_verified": compression.get("all_verified") is True,
            "storage_split_verified": split.get("all_verified") is True,
            "compressed_item_count": compression.get("item_count"),
            "removed_reconstructable_source_snapshots": removed,
            "errors": [],
        }
        if not audit["ok"]:
            raise RuntimeError(f"{context['tag']}: compression verification failed")
        write_json(context["output"] / "post-run-audit.json", audit)

    commits = {}
    for context in contexts:
        commits[context["tag"]] = git_save(context, args.push)
    print(json.dumps({"eval": args.eval, "status": "completed", "commits": commits}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

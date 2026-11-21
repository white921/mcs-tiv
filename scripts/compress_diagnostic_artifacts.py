#!/usr/bin/env python3
"""Reproducibly compress and verify diagnostic traces and checkpoints."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import subprocess


JSONL_NAMES = ("conflicts.jsonl", "vehicle-states.jsonl", "prediction-events.jsonl")
CHUNK_SIZE = 80_000_000
SPLIT_THRESHOLD = 100_000_000


def digest(path: Path, *, count_lines: bool = False) -> tuple[str, int, int | None]:
    hasher = hashlib.sha256()
    size = 0
    lines = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
            size += len(block)
            if count_lines:
                lines += block.count(b"\n")
    return hasher.hexdigest(), size, lines if count_lines else None


def restored_digest(path: Path, *, codec: str, count_lines: bool) -> tuple[str, int, int | None]:
    opener = gzip.open if codec == "gzip" else lzma.open
    hasher = hashlib.sha256()
    size = 0
    lines = 0
    with opener(path, "rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
            size += len(block)
            if count_lines:
                lines += block.count(b"\n")
    return hasher.hexdigest(), size, lines if count_lines else None


def compress_one(task: tuple[Path, Path, str]) -> dict[str, object]:
    root, source, codec = task
    relative = source.relative_to(root)
    suffix = ".gz" if codec == "gzip" else ".xz"
    compressed = source.with_name(source.name + suffix)
    temporary = compressed.with_name(compressed.name + ".tmp")
    count_lines = source.suffix == ".jsonl"
    original_sha, original_size, original_lines = digest(source, count_lines=count_lines)
    command = ["gzip", "-n", "-6", "-c", str(source)] if codec == "gzip" else ["xz", "-T1", "-6", "-c", str(source)]
    with temporary.open("wb") as output:
        subprocess.run(command, check=True, stdout=output)
    os.replace(temporary, compressed)
    compressed_sha, compressed_size, _ = digest(compressed)
    restored_sha, restored_size, restored_lines = restored_digest(
        compressed, codec=codec, count_lines=count_lines
    )
    verified = (
        original_sha == restored_sha
        and original_size == restored_size
        and original_lines == restored_lines
    )
    if not verified:
        raise RuntimeError(f"round-trip verification failed: {relative}")
    source.unlink()
    item: dict[str, object] = {
        "kind": f"{source.suffix.removeprefix('.')}-{codec}",
        "source": str(relative),
        "compressed": str(compressed.relative_to(root)),
        "command_equivalent": "gzip -n -6" if codec == "gzip" else "xz -T1 -6",
        "original_sha256": original_sha,
        "original_size_bytes": original_size,
        "compressed_sha256": compressed_sha,
        "compressed_size_bytes": compressed_size,
        "restored_sha256": restored_sha,
        "restored_size_bytes": restored_size,
        "verified": True,
    }
    if count_lines:
        item["original_line_count"] = original_lines
        item["restored_line_count"] = restored_lines
    return item


def split_one(root: Path, compressed: Path) -> dict[str, object] | None:
    source_sha, source_size, _ = digest(compressed)
    if source_size <= SPLIT_THRESHOLD:
        return None
    parts = []
    with compressed.open("rb") as source:
        index = 0
        while block := source.read(CHUNK_SIZE):
            part = compressed.with_name(f"{compressed.name}.part-{index:03d}")
            with part.open("wb") as output:
                output.write(block)
            part_sha, part_size, _ = digest(part)
            parts.append({
                "path": str(part.relative_to(root)),
                "sha256": part_sha,
                "size_bytes": part_size,
            })
            index += 1
    restored_hasher = hashlib.sha256()
    restored_size = 0
    for item in parts:
        with (root / str(item["path"])).open("rb") as stream:
            while block := stream.read(1024 * 1024):
                restored_hasher.update(block)
                restored_size += len(block)
    if restored_hasher.hexdigest() != source_sha or restored_size != source_size:
        raise RuntimeError(f"split verification failed: {compressed}")
    compressed.unlink()
    return {
        "source_path": str(compressed.relative_to(root)),
        "source_sha256": source_sha,
        "source_size_bytes": source_size,
        "chunk_size_bytes": CHUNK_SIZE,
        "part_count": len(parts),
        "parts": parts,
        "restored_sha256": restored_hasher.hexdigest(),
        "restored_size_bytes": restored_size,
        "verified": True,
    }


def process(root: Path, workers: int) -> None:
    runs = sorted(root.glob("eval7/seed-*"))
    if not runs:
        raise RuntimeError(f"no runs found under {root}")
    tasks: list[tuple[Path, Path, str]] = []
    for run in runs:
        tasks.extend((root, run / name, "gzip") for name in JSONL_NAMES)
        checkpoints = sorted((run / "checkpoints").glob("t*/mcs-state.pkl"))
        if len(checkpoints) != 10:
            raise RuntimeError(f"expected 10 checkpoint states under {run}, found {len(checkpoints)}")
        tasks.extend((root, path, "xz") for path in checkpoints)
    missing = [str(path) for _, path, _ in tasks if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing source artifacts: {missing[:5]}")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        items = list(executor.map(compress_one, tasks))
    items.sort(key=lambda item: str(item["source"]))
    compression = {
        "schema_version": 1,
        "all_verified": all(bool(item["verified"]) for item in items),
        "item_count": len(items),
        "run_count": len(runs),
        "expected_items_per_run": 13,
        "commands": {"jsonl": "gzip -n -6", "checkpoint": "xz -T1 -6"},
        "original_size_bytes": sum(int(item["original_size_bytes"]) for item in items),
        "compressed_size_bytes": sum(int(item["compressed_size_bytes"]) for item in items),
        "items": items,
    }
    (root / "compression-audit.json").write_text(
        json.dumps(compression, indent=2) + "\n", encoding="utf-8"
    )

    split_items = []
    for item in items:
        path = root / str(item["compressed"])
        split = split_one(root, path)
        if split is not None:
            split_items.append(split)
    split_audit = {
        "schema_version": 1,
        "all_verified": all(bool(item["verified"]) for item in split_items),
        "threshold_bytes": SPLIT_THRESHOLD,
        "chunk_size_bytes": CHUNK_SIZE,
        "item_count": len(split_items),
        "items": split_items,
    }
    (root / "storage-split-audit.json").write_text(
        json.dumps(split_audit, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    process(args.root.resolve(), args.workers)


if __name__ == "__main__":
    main()

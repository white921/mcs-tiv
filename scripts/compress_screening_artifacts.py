#!/usr/bin/env python3
"""Compress and audit large screening artifacts in a finished experiment."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess


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


def restored_digest(path: Path, *, count_lines: bool) -> tuple[str, int, int | None]:
    hasher = hashlib.sha256()
    size = 0
    lines = 0
    with gzip.open(path, "rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
            size += len(block)
            if count_lines:
                lines += block.count(b"\n")
    return hasher.hexdigest(), size, lines if count_lines else None


def compress_one(root: Path, source: Path) -> dict[str, object]:
    relative = source.relative_to(root)
    compressed = source.with_name(source.name + ".gz")
    temporary = compressed.with_name(compressed.name + ".tmp")
    count_lines = source.suffix in {".jsonl", ".xml"}
    original_sha, original_size, original_lines = digest(
        source, count_lines=count_lines
    )
    with temporary.open("wb") as output:
        subprocess.run(
            ["gzip", "-n", "-6", "-c", str(source)],
            check=True,
            stdout=output,
        )
    os.replace(temporary, compressed)
    compressed_sha, compressed_size, _ = digest(compressed)
    restored_sha, restored_size, restored_lines = restored_digest(
        compressed, count_lines=count_lines
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
        "kind": f"{source.suffix.removeprefix('.')}-gzip",
        "source": str(relative),
        "compressed": str(compressed.relative_to(root)),
        "command_equivalent": "gzip -n -6",
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
            part.write_bytes(block)
            part_sha, part_size, _ = digest(part)
            parts.append(
                {
                    "path": str(part.relative_to(root)),
                    "sha256": part_sha,
                    "size_bytes": part_size,
                }
            )
            index += 1
    hasher = hashlib.sha256()
    restored_size = 0
    for item in parts:
        part = root / str(item["path"])
        with part.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                hasher.update(block)
                restored_size += len(block)
    restored_sha = hasher.hexdigest()
    verified = restored_sha == source_sha and restored_size == source_size
    if not verified:
        raise RuntimeError(f"split verification failed: {compressed}")
    compressed.unlink()
    return {
        "source_path": str(compressed.relative_to(root)),
        "source_sha256": source_sha,
        "source_size_bytes": source_size,
        "chunk_size_bytes": CHUNK_SIZE,
        "part_count": len(parts),
        "parts": parts,
        "restored_sha256": restored_sha,
        "restored_size_bytes": restored_size,
        "verified": True,
    }


def process(root: Path, workers: int) -> None:
    sources = sorted(root.glob("eval7/seed-*/prediction-events.jsonl"))
    sources += sorted(root.glob("eval7/seed-*/source/merge/statistics/sumoStat.xml"))
    if len(sources) != 20:
        raise RuntimeError(f"expected 20 source artifacts under {root}, found {len(sources)}")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        items = list(executor.map(lambda path: compress_one(root, path), sources))
    items.sort(key=lambda item: str(item["source"]))
    compression = {
        "all_verified": all(bool(item["verified"]) for item in items),
        "compression": "gzip -n -6",
        "item_count": len(items),
        "original_size_bytes": sum(int(item["original_size_bytes"]) for item in items),
        "compressed_size_bytes": sum(int(item["compressed_size_bytes"]) for item in items),
        "items": items,
    }
    (root / "compression-audit.json").write_text(
        json.dumps(compression, indent=2) + "\n", encoding="utf-8"
    )

    compressed_paths = [root / str(item["compressed"]) for item in items]
    split_items = []
    for path in compressed_paths:
        split = split_one(root, path)
        if split is not None:
            split_items.append(split)
    split_audit = {
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
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    process(args.root.resolve(), args.workers)


if __name__ == "__main__":
    main()

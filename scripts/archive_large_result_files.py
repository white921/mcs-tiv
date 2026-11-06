#!/usr/bin/env python3
"""Create auditable Git-safe copies of oversized result files.

The source files are never removed or modified.  Each oversized file is gzip
compressed with a deterministic header, split when necessary, and recorded in
a SHA-256 manifest.  A root .gitignore keeps the preserved originals local.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path


ARCHIVE_DIRECTORY = "large-file-archive"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compress(source: Path, destination: Path, level: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_stream, destination.open("wb") as output_stream:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=level,
            fileobj=output_stream,
            mtime=0,
        ) as gzip_stream:
            shutil.copyfileobj(input_stream, gzip_stream, length=1024 * 1024)


def split_file(source: Path, prefix: Path, chunk_size: int) -> list[Path]:
    parts = []
    with source.open("rb") as stream:
        index = 1
        while block := stream.read(chunk_size):
            part = Path(f"{prefix}.part{index:04d}")
            part.parent.mkdir(parents=True, exist_ok=True)
            part.write_bytes(block)
            parts.append(part)
            index += 1
    return parts


def archive_run(
    root: Path,
    *,
    threshold_bytes: int,
    chunk_size_bytes: int,
    compression_level: int,
) -> dict:
    root = root.resolve()
    archive_root = root / ARCHIVE_DIRECTORY
    if archive_root.exists():
        raise FileExistsError(f"archive already exists: {archive_root}")
    if not root.is_dir():
        raise NotADirectoryError(root)
    if chunk_size_bytes >= threshold_bytes:
        raise ValueError("chunk size must be smaller than the threshold")

    sources = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and ARCHIVE_DIRECTORY not in path.relative_to(root).parts
        and path.name != ".gitignore"
        and path.stat().st_size >= threshold_bytes
    )
    entries = []
    ignored = []
    temporary = archive_root / ".tmp"
    try:
        for source in sources:
            relative = source.relative_to(root)
            compressed_relative = Path("files") / Path(f"{relative}.gz")
            compressed = archive_root / compressed_relative
            temporary_file = temporary / Path(f"{relative}.gz")
            compress(source, temporary_file, compression_level)
            gzip_size = temporary_file.stat().st_size
            gzip_hash = sha256(temporary_file)
            if gzip_size < threshold_bytes:
                compressed.parent.mkdir(parents=True, exist_ok=True)
                temporary_file.replace(compressed)
                parts = [compressed]
            else:
                parts = split_file(temporary_file, compressed, chunk_size_bytes)
                temporary_file.unlink()
            part_records = [
                {
                    "path": str(path.relative_to(root)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
                for path in parts
            ]
            if any(item["size_bytes"] >= threshold_bytes for item in part_records):
                raise ValueError(f"archive part exceeds threshold: {relative}")
            entries.append({
                "source_path": str(relative),
                "source_size_bytes": source.stat().st_size,
                "source_sha256": sha256(source),
                "gzip_size_bytes": gzip_size,
                "gzip_sha256": gzip_hash,
                "parts": part_records,
            })
            ignored.append(f"/{relative}")
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    manifest = {
        "schema": "large-result-file-archive-v1",
        "run_directory": root.name,
        "originals_preserved_locally": True,
        "threshold_bytes": threshold_bytes,
        "chunk_size_bytes": chunk_size_bytes,
        "compression": {"format": "gzip", "level": compression_level, "mtime": 0},
        "oversized_file_count": len(entries),
        "entries": entries,
    }
    archive_root.mkdir(parents=True, exist_ok=True)
    (archive_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text("\n".join(ignored) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--threshold-bytes", type=int, default=95_000_000)
    parser.add_argument("--chunk-size-bytes", type=int, default=90_000_000)
    parser.add_argument("--compression-level", type=int, default=1, choices=range(1, 10))
    args = parser.parse_args()
    manifest = archive_run(
        args.run_directory,
        threshold_bytes=args.threshold_bytes,
        chunk_size_bytes=args.chunk_size_bytes,
        compression_level=args.compression_level,
    )
    print(json.dumps({
        "run_directory": manifest["run_directory"],
        "oversized_file_count": manifest["oversized_file_count"],
        "originals_preserved_locally": manifest["originals_preserved_locally"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

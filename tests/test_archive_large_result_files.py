import gzip
import hashlib
import json
import random
import tempfile
import unittest
from pathlib import Path

from scripts.archive_large_result_files import archive_run


class ArchiveLargeResultFilesTests(unittest.TestCase):
    def test_preserves_sources_and_records_reconstructable_parts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            compressible = root / "case" / "large.jsonl"
            split_source = root / "case" / "state.pkl"
            small = root / "case" / "small.log"
            compressible.parent.mkdir(parents=True)
            compressible.write_bytes(b'{"value": 1}\n' * 2_000)
            split_source.write_bytes(random.Random(7).randbytes(20_000))
            small.write_text("small\n", encoding="utf-8")
            source_hashes = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (compressible, split_source)
            }

            manifest = archive_run(
                root,
                threshold_bytes=10_000,
                chunk_size_bytes=4_000,
                compression_level=1,
            )

            self.assertEqual(manifest["oversized_file_count"], 2)
            self.assertTrue(compressible.exists())
            self.assertTrue(split_source.exists())
            self.assertEqual(small.read_text(encoding="utf-8"), "small\n")
            self.assertEqual(
                (root / ".gitignore").read_text(encoding="utf-8").splitlines(),
                ["/case/large.jsonl", "/case/state.pkl"],
            )
            saved = json.loads(
                (root / "large-file-archive" / "manifest.json").read_text()
            )
            for entry in saved["entries"]:
                source = root / entry["source_path"]
                self.assertEqual(entry["source_sha256"], source_hashes[source])
                compressed = b"".join(
                    (root / part["path"]).read_bytes() for part in entry["parts"]
                )
                self.assertEqual(
                    hashlib.sha256(compressed).hexdigest(), entry["gzip_sha256"]
                )
                self.assertEqual(gzip.decompress(compressed), source.read_bytes())
                self.assertTrue(all(
                    part["size_bytes"] < saved["threshold_bytes"]
                    for part in entry["parts"]
                ))


if __name__ == "__main__":
    unittest.main()

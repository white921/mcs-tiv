from pathlib import Path
import tempfile
import unittest

from scripts import audit_experiment_ledger as audit


class AuditExperimentLedgerTest(unittest.TestCase):
    def test_reads_inline_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.md"
            path.write_text("- 状態: `completed`\n", encoding="utf-8")
            self.assertEqual(audit.record_state(path), "completed")

    def test_reads_bulleted_state_block(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.md"
            path.write_text("## 状態\n\n- `completed`\n", encoding="utf-8")
            self.assertEqual(audit.record_state(path), "completed")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from rl_kyc_task_env.datasets import get_split_paths, list_documents, load_document
from rl_kyc_task_env.paths import REPO_ROOT
from rl_kyc_task_env.records import DocumentRecord, SplitPaths


class DatasetRecordsTest(unittest.TestCase):
    def test_missing_installed_dataset_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "val"
            with patch("rl_kyc_task_env.datasets.get_split_paths", return_value=SplitPaths("val", missing)):
                with self.assertRaisesRegex(FileNotFoundError, "RL_KYC_DATA_ROOT"):
                    list_documents("val")

    def test_val_split_lists_document_records(self) -> None:
        records = list_documents("val")
        self.assertEqual(len(records), 90)
        self.assertIsInstance(records[0], DocumentRecord)
        self.assertEqual(records[0].split, "val")
        self.assertTrue(records[0].document_dir.is_dir())
        self.assertTrue(records[0].gold_path.is_file())

    def test_hidden_split_resolves_hidden_gold(self) -> None:
        paths = get_split_paths("hidden_test")
        self.assertEqual(paths.dataset_dir, REPO_ROOT / "private" / "hidden_test")
        self.assertEqual(paths.gold_dir, REPO_ROOT / "private" / "hidden_gold")
        records = list_documents("hidden_test", limit=2)
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0].gold_path.is_file())

    def test_load_document_returns_metadata_ocr_and_gold(self) -> None:
        record = list_documents("val", limit=1)[0]
        document = load_document(record)
        self.assertEqual(document.record.doc_id, record.doc_id)
        self.assertIn("schema_name", document.meta)
        self.assertIn("pages", document.ocr)
        self.assertIn("fields", document.gold)


if __name__ == "__main__":
    unittest.main()

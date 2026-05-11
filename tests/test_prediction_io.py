from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from task.tools.eval_core import evaluate_document, run_prediction_subprocess


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "task" / "public_data" / "val" / "doc_000000"


class PredictionIoTest(unittest.TestCase):
    def test_missing_extract_reports_missing_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status, prediction = run_prediction_subprocess(Path(tmp_dir), DOCUMENT)
        self.assertEqual(status, "missing_extract")
        self.assertIsNone(prediction)

    def test_non_serializable_prediction_reports_non_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            solution_dir = Path(tmp_dir)
            (solution_dir / "extract.py").write_text(
                "def predict(document_dir):\n    return {'bad': {1, 2}}\n",
                encoding="utf-8",
            )
            status, prediction = run_prediction_subprocess(solution_dir, DOCUMENT)
        self.assertEqual(status, "non_serializable")
        self.assertIsNone(prediction)

    def test_runtime_exception_reports_runtime_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            solution_dir = Path(tmp_dir)
            (solution_dir / "extract.py").write_text(
                "def predict(document_dir):\n    raise RuntimeError('boom')\n",
                encoding="utf-8",
            )
            status, prediction = run_prediction_subprocess(solution_dir, DOCUMENT)
        self.assertEqual(status, "runtime_exception")
        self.assertIsNone(prediction)

    def test_invalid_schema_scores_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            solution_dir = Path(tmp_dir)
            (solution_dir / "extract.py").write_text(
                "def predict(document_dir):\n    return {'schema_name': 'government_id'}\n",
                encoding="utf-8",
            )
            result = evaluate_document(solution_dir, DOCUMENT)
        self.assertEqual(result["status"], "invalid_schema")
        self.assertEqual(result["score"], 0.0)

    def test_valid_null_baseline_returns_ok_status(self) -> None:
        result = evaluate_document(ROOT / "baselines" / "null_baseline", DOCUMENT)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["score"], 0.0)


if __name__ == "__main__":
    unittest.main()

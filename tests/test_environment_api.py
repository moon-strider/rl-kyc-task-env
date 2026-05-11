from __future__ import annotations

import json
import unittest

from rl_kyc_task_env.environment import DocumentExtractionTask
from rl_kyc_task_env.prediction_io import parse_prediction, prediction_from_fields
from rl_kyc_task_env.prompts import build_document_prompt, reconstruct_ocr_lines


class EnvironmentApiTest(unittest.TestCase):
    def test_task_loads_limited_records_and_observation(self) -> None:
        task = DocumentExtractionTask(split="val", limit=2)
        self.assertEqual(len(task.records), 2)
        observation = task.get_observation(task.records[0])
        self.assertEqual(observation["doc_id"], task.records[0].doc_id)
        self.assertEqual(observation["schema_name"], task.records[0].schema_name)
        self.assertIn("fields", observation)
        self.assertIn("ocr_lines", observation)

    def test_score_submission_accepts_gold_prediction(self) -> None:
        task = DocumentExtractionTask(split="val", limit=1)
        record = task.records[0]
        document = task.load_document(record)
        result = task.score_submission(record, document.gold)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.reward, 1.0)

    def test_text_submission_parses_json_and_scores(self) -> None:
        task = DocumentExtractionTask(split="val", limit=1)
        record = task.records[0]
        document = task.load_document(record)
        result = task.evaluate_text_submission(record, f"```json\n{json.dumps(document.gold)}\n```")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.reward, 1.0)

    def test_invalid_submission_returns_zero_reward(self) -> None:
        task = DocumentExtractionTask(split="val", limit=1)
        record = task.records[0]
        result = task.score_submission(record, {"schema_name": record.schema_name, "fields": {}})
        self.assertEqual(result.status, "invalid_schema")
        self.assertEqual(result.reward, 0.0)

    def test_prompt_contains_schema_fields_and_ocr_lines(self) -> None:
        task = DocumentExtractionTask(split="val", limit=1)
        record = task.records[0]
        prompt = build_document_prompt(record)
        self.assertIn(record.schema_name, prompt)
        self.assertIn("Return only JSON", prompt)
        self.assertIn("OCR lines", prompt)

    def test_prediction_helpers_parse_fenced_json(self) -> None:
        prediction = parse_prediction('before ```json\n{"schema_name":"x","fields":{}}\n``` after')
        self.assertEqual(prediction, {"schema_name": "x", "fields": {}})
        self.assertEqual(prediction_from_fields("x", {"a": "b"}), {"schema_name": "x", "fields": {"a": "b"}})

    def test_reconstruct_ocr_lines_returns_text_lines(self) -> None:
        task = DocumentExtractionTask(split="val", limit=1)
        document = task.load_document(task.records[0])
        lines = reconstruct_ocr_lines(document.ocr)
        self.assertGreater(len(lines), 0)
        self.assertIn("text", lines[0])


if __name__ == "__main__":
    unittest.main()

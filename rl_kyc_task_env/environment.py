from __future__ import annotations

from typing import Any

from .datasets import list_documents, load_document
from .prediction_io import parse_prediction
from .prompts import reconstruct_ocr_lines
from .records import Document, DocumentRecord, SubmissionScore
from .schemas import field_names, load_schema, validate_prediction
from .scoring import score_prediction


class DocumentExtractionTask:
    def __init__(
        self,
        split: str = "train",
        limit: int | None = None,
        indices: list[int] | tuple[int, ...] | None = None,
        schemas: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.split = split
        self.records = list_documents(split, limit=limit, indices=indices, schemas=schemas)

    def load_document(self, record: DocumentRecord) -> Document:
        return load_document(record)

    def get_observation(self, record: DocumentRecord, ocr_format: str = "lines") -> dict[str, Any]:
        document = self.load_document(record)
        observation: dict[str, Any] = {
            "doc_id": record.doc_id,
            "schema_name": record.schema_name,
            "fields": field_names(record.schema_name),
            "schema": load_schema(record.schema_name),
            "meta": document.meta,
        }
        if ocr_format == "raw":
            observation["ocr"] = document.ocr
        elif ocr_format == "lines":
            observation["ocr_lines"] = reconstruct_ocr_lines(document.ocr)
        else:
            raise ValueError(f"Unknown OCR format: {ocr_format}")
        return observation

    def score_submission(self, record: DocumentRecord, prediction: Any) -> SubmissionScore:
        document = self.load_document(record)
        parsed = parse_prediction(prediction)
        if parsed is None:
            return SubmissionScore(record.schema_name, 0.0, "unparseable_prediction", 0.0, None)
        if document.gold is None:
            return SubmissionScore(record.schema_name, 0.0, "missing_gold", 0.0, parsed)
        if not validate_prediction(record.schema_name, parsed):
            return SubmissionScore(record.schema_name, 0.0, "invalid_schema", 0.0, parsed)
        score = score_prediction(record.schema_name, parsed, document.gold)
        return SubmissionScore(record.schema_name, score, "ok", score, parsed)

    def evaluate_text_submission(self, record: DocumentRecord, text: str) -> SubmissionScore:
        return self.score_submission(record, text)

    def submit(self, record: DocumentRecord, payload: Any) -> dict[str, Any]:
        result = self.score_submission(record, payload)
        return {
            "reward": result.reward,
            "finished": True,
            "status": result.status,
            "schema_name": result.schema_name,
            "score": result.score,
        }

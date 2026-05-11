from __future__ import annotations

from .paths import REPO_ROOT
from .records import Document, DocumentRecord, SplitPaths
from .datasets import get_split_paths, list_documents, load_document, load_json
from .environment import DocumentExtractionTask
from .evaluation import evaluate_document, evaluate_solution
from .scoring import aggregate_scores, score_prediction, validate_prediction
from .schemas import field_names, load_schema, schema_names

__all__ = [
    "Document",
    "DocumentExtractionTask",
    "DocumentRecord",
    "REPO_ROOT",
    "SplitPaths",
    "aggregate_scores",
    "evaluate_document",
    "evaluate_solution",
    "field_names",
    "get_split_paths",
    "list_documents",
    "load_document",
    "load_json",
    "load_schema",
    "schema_names",
    "score_prediction",
    "validate_prediction",
]

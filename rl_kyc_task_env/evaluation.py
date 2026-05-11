from __future__ import annotations

from pathlib import Path
from typing import Any

from .datasets import list_document_dirs, load_json, resolve_gold_path
from .runner import TIMEOUT_SECONDS, run_prediction_subprocess
from .scoring import aggregate_scores, score_prediction, validate_prediction


def evaluate_document(
    solution_dir: Path,
    document_dir: Path,
    gold_dir: Path | None = None,
) -> dict[str, Any]:
    meta = load_json(document_dir / "meta.json")
    schema_name = meta["schema_name"]
    gold = load_json(resolve_gold_path(document_dir, gold_dir))
    status, prediction = run_prediction_subprocess(solution_dir, document_dir)
    if status != "ok":
        return {"schema_name": schema_name, "score": 0.0, "status": status}
    if not validate_prediction(schema_name, prediction):
        return {"schema_name": schema_name, "score": 0.0, "status": "invalid_schema"}
    return {"schema_name": schema_name, "score": score_prediction(schema_name, prediction, gold), "status": "ok"}


def evaluate_solution(
    solution_dir: Path,
    dataset_dir: Path,
    gold_dir: Path | None = None,
    include_error_summary: bool = False,
) -> dict[str, Any]:
    doc_results = [
        evaluate_document(solution_dir, document_dir, gold_dir)
        for document_dir in list_document_dirs(dataset_dir)
    ]
    return aggregate_scores(doc_results, include_error_summary=include_error_summary)


__all__ = [
    "TIMEOUT_SECONDS",
    "aggregate_scores",
    "evaluate_document",
    "evaluate_solution",
    "list_document_dirs",
    "load_json",
    "resolve_gold_path",
    "run_prediction_subprocess",
    "score_prediction",
    "validate_prediction",
]

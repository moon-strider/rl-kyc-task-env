from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from task.tools.canonicalize import canonicalize_prediction

from .schemas import SCHEMA_NAMES, validate_prediction


def score_prediction(schema_name: str, prediction: dict[str, Any], gold: dict[str, Any]) -> float:
    canonical_prediction = canonicalize_prediction(prediction)
    canonical_gold = canonicalize_prediction(gold)
    gold_fields = canonical_gold["fields"]
    prediction_fields = canonical_prediction["fields"]
    field_names = list(gold_fields.keys())
    matches = [
        1.0 if prediction_fields.get(field_name) == gold_fields.get(field_name) else 0.0
        for field_name in field_names
    ]
    field_acc = sum(matches) / len(matches)
    exact_doc = 1.0 if all(match == 1.0 for match in matches) else 0.0
    return 0.9 * field_acc + 0.1 * exact_doc


def _rounded(value: float) -> float:
    return round(value, 4)


def aggregate_scores(
    doc_results: list[dict[str, Any]],
    include_error_summary: bool = False,
) -> dict[str, Any]:
    by_schema_docs: dict[str, list[float]] = defaultdict(list)
    status_counts: Counter[str] = Counter()
    for result in doc_results:
        by_schema_docs[result["schema_name"]].append(result["score"])
        status_counts[result["status"]] += 1

    raw_by_schema = {}
    by_schema = {}
    for schema_name in SCHEMA_NAMES:
        schema_scores = by_schema_docs.get(schema_name, [])
        schema_score = sum(schema_scores) / len(schema_scores) if schema_scores else 0.0
        raw_by_schema[schema_name] = schema_score
        by_schema[schema_name] = _rounded(schema_score)

    final_score = sum(raw_by_schema[schema_name] for schema_name in SCHEMA_NAMES) / len(SCHEMA_NAMES)
    result = {
        "score": _rounded(final_score),
        "by_schema": by_schema,
        "num_docs": len(doc_results),
    }
    if include_error_summary:
        result["error_summary"] = {
            status: count
            for status, count in sorted(status_counts.items())
            if status != "ok" and count > 0
        }
    return result


__all__ = ["aggregate_scores", "score_prediction", "validate_prediction"]

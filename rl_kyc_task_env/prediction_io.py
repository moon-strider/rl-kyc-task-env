from __future__ import annotations

import json
import re
from typing import Any


def extract_json_text(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def parse_prediction(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return payload
    if not isinstance(payload, str):
        return None
    try:
        parsed = json.loads(extract_json_text(payload))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def prediction_from_fields(schema_name: str, fields: dict[str, Any]) -> dict[str, Any]:
    return {"schema_name": schema_name, "fields": fields}


MAX_PREDICTION_FILE_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_PREDICTION_BYTES = 64 * 1024
MAX_JSON_DEPTH = 16
PREDICTION_STATUSES = frozenset({
    "ok", "missing_extract", "import_failure", "runtime_exception",
    "non_serializable", "timeout", "output_limit", "invalid_prediction", "missing_prediction",
})


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _check_json_tree(value: Any, depth: int = 0) -> None:
    import math

    if depth > MAX_JSON_DEPTH:
        raise ValueError("Prediction JSON is too deeply nested")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite JSON number")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Invalid Unicode in prediction") from exc
    if isinstance(value, dict):
        for key, child in value.items():
            _check_json_tree(key, depth + 1)
            _check_json_tree(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_json_tree(child, depth + 1)


def parse_prediction_envelope(
    text: str, expected_doc_ids: set[str] | None = None
) -> dict[str, Any]:
    """Validate untrusted collector output as plain, bounded JSON data."""
    if len(text.encode("utf-8")) > MAX_PREDICTION_FILE_BYTES:
        raise ValueError("Prediction file exceeds size limit")
    try:
        envelope = json.loads(text, object_pairs_hook=_strict_pairs, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError("Invalid prediction JSON") from exc
    _check_json_tree(envelope)
    if not isinstance(envelope, dict) or set(envelope) != {"version", "documents"}:
        raise ValueError("Expected version and documents in prediction envelope")
    if type(envelope["version"]) is not int or envelope["version"] != 1:
        raise ValueError("Unsupported prediction version")
    documents = envelope["documents"]
    if not isinstance(documents, dict) or len(documents) > 10000:
        raise ValueError("Invalid document predictions")
    for doc_id, record in documents.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", doc_id):
            raise ValueError("Invalid document identifier")
        if expected_doc_ids is not None and doc_id not in expected_doc_ids:
            raise ValueError("Unexpected document identifier")
        if not isinstance(record, dict) or not isinstance(record.get("status"), str) or record["status"] not in PREDICTION_STATUSES:
            raise ValueError("Invalid prediction status")
        expected_keys = {"status", "prediction"} if record["status"] == "ok" else {"status"}
        if set(record) != expected_keys:
            raise ValueError("Invalid prediction record")
        if len(json.dumps(record, ensure_ascii=False).encode("utf-8")) > MAX_DOCUMENT_PREDICTION_BYTES:
            raise ValueError("Document prediction exceeds size limit")
    return envelope


def load_prediction_file(path, expected_doc_ids: set[str] | None = None) -> dict[str, Any]:
    """Read a regular JSON file; never follow an attacker-controlled symlink."""
    import os
    import stat

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Prediction input must be a regular file")
        data = handle.read(MAX_PREDICTION_FILE_BYTES + 1)
    if len(data) > MAX_PREDICTION_FILE_BYTES:
        raise ValueError("Prediction file exceeds size limit")
    return parse_prediction_envelope(data.decode("utf-8"), expected_doc_ids)


def write_prediction_file(path, envelope: dict[str, Any]) -> None:
    """Persist a validated envelope compactly without inflating bounded input."""
    text = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    parse_prediction_envelope(text)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)

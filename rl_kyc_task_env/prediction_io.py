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

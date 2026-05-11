from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft7Validator

from .paths import SCHEMA_DIR

SCHEMA_NAMES = ("government_id", "proof_of_address", "payment_receipt")


def schema_names() -> tuple[str, ...]:
    return SCHEMA_NAMES


@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict[str, Any]:
    if schema_name not in SCHEMA_NAMES:
        raise KeyError(schema_name)
    path = SCHEMA_DIR / f"{schema_name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def schema_validator(schema_name: str) -> Draft7Validator:
    return Draft7Validator(load_schema(schema_name))


def field_names(schema_name: str) -> tuple[str, ...]:
    schema = load_schema(schema_name)
    return tuple(schema["properties"]["fields"]["required"])


def validate_prediction(schema_name: str, prediction: Any) -> bool:
    return schema_validator(schema_name).is_valid(prediction)

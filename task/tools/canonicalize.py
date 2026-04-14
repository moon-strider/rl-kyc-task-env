from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

DATE_FIELDS = {
    "date_of_birth",
    "issue_date",
    "expiry_date",
    "statement_date",
    "payment_date",
}
IDENTIFIER_FIELDS = {"document_number", "reference_id"}
POSTAL_CODE_FIELDS = {"postal_code"}
AMOUNT_FIELDS = {"amount"}
CURRENCY_FIELDS = {"currency"}

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
)
_AMOUNT_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_WHITESPACE_RE = re.compile(r"\s+")
_CURRENCY_MAP = {
    "$": "USD",
    "usd": "USD",
    "us dollar": "USD",
    "us dollars": "USD",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "pound sterling": "GBP",
    "pounds sterling": "GBP",
}


def _strip_edge_punctuation(text: str) -> str:
    start = 0
    end = len(text)
    while start < end and unicodedata.category(text[start]).startswith("P"):
        start += 1
    while end > start and unicodedata.category(text[end - 1]).startswith("P"):
        end -= 1
    return text[start:end]


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)
    text = text.strip()
    text = _WHITESPACE_RE.sub(" ", text)
    text = _strip_edge_punctuation(text)
    text = text.strip()
    return text


def canonicalize_date(value: str) -> str:
    normalized = normalize_text(value)
    candidates = [normalized]
    title_cased = normalized.title()
    if title_cased != normalized:
        candidates.append(title_cased)

    for candidate in candidates:
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return normalized


def canonicalize_amount(value: str) -> str:
    normalized = normalize_text(value)
    numbers = _AMOUNT_NUMBER_RE.findall(normalized.replace(",", ""))
    if len(numbers) != 1:
        return normalized
    try:
        amount = Decimal(numbers[0]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return normalized
    return f"{amount:.2f}"


def canonicalize_currency(value: str) -> str:
    normalized = normalize_text(value)
    key = normalized.casefold()
    return _CURRENCY_MAP.get(key, normalized.upper())


def canonicalize_identifier(value: str) -> str:
    normalized = normalize_text(value)
    normalized = normalized.replace(" ", "")
    return normalized.upper()


def canonicalize_postal_code(value: str) -> str:
    normalized = normalize_text(value).upper()
    return normalized


def canonicalize_ordinary_text(value: str) -> str:
    normalized = normalize_text(value)
    return normalized.casefold()


def canonicalize_value(field_name: str, value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    if field_name in DATE_FIELDS:
        return canonicalize_date(value)
    if field_name in AMOUNT_FIELDS:
        return canonicalize_amount(value)
    if field_name in CURRENCY_FIELDS:
        return canonicalize_currency(value)
    if field_name in IDENTIFIER_FIELDS:
        return canonicalize_identifier(value)
    if field_name in POSTAL_CODE_FIELDS:
        return canonicalize_postal_code(value)
    return canonicalize_ordinary_text(value)


def canonicalize_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    fields = prediction.get("fields", {})
    canonical_fields = {
        field_name: canonicalize_value(field_name, field_value)
        for field_name, field_value in fields.items()
    }
    return {
        "schema_name": prediction.get("schema_name"),
        "fields": canonical_fields,
    }


__all__ = [
    "AMOUNT_FIELDS",
    "CURRENCY_FIELDS",
    "DATE_FIELDS",
    "IDENTIFIER_FIELDS",
    "POSTAL_CODE_FIELDS",
    "canonicalize_amount",
    "canonicalize_currency",
    "canonicalize_date",
    "canonicalize_identifier",
    "canonicalize_ordinary_text",
    "canonicalize_postal_code",
    "canonicalize_prediction",
    "canonicalize_value",
    "normalize_text",
]

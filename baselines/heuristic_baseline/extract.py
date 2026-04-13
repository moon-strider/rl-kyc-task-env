from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task.tools.canonicalize import canonicalize_value

SCHEMA_FIELDS = {
    "government_id": [
        "full_name",
        "date_of_birth",
        "document_number",
        "issue_date",
        "expiry_date",
        "issuing_country",
    ],
    "proof_of_address": [
        "full_name",
        "address_line1",
        "city",
        "postal_code",
        "country",
        "statement_date",
        "issuer_name",
    ],
    "payment_receipt": [
        "sender_name",
        "recipient_name",
        "amount",
        "currency",
        "payment_date",
        "reference_id",
    ],
}

LABELS = {
    "government_id": {
        "full_name": ["Name", "Full Name", "Holder Name", "Surname and Given Names"],
        "date_of_birth": ["Date of Birth", "DOB", "Birth Date"],
        "document_number": ["Document No.", "Passport No.", "ID Number", "Doc No."],
        "issue_date": ["Issue Date", "Date of Issue", "Issued On"],
        "expiry_date": ["Expiry Date", "Date of Expiry", "Valid Until"],
        "issuing_country": ["Issuing Country", "Country of Issue", "Issued In"],
    },
    "proof_of_address": {
        "statement_date": ["Statement Date", "Bill Date", "Issued On"],
    },
    "payment_receipt": {
        "sender_name": ["From", "Sender", "Paid By", "Payer"],
        "recipient_name": ["To", "Recipient", "Merchant", "Payee"],
        "amount": ["Amount", "Total Paid", "Payment Amount", "Total"],
        "payment_date": ["Payment Date", "Date", "Processed On"],
        "reference_id": ["Reference", "Transaction ID", "Payment Ref", "Ref ID"],
        "currency": ["Currency"],
    },
}

POA_ANCHORS = ["Bill To", "Customer Name", "Account Holder", "Service Address", "Mailing Address", "Address"]
KNOWN_COUNTRIES = ["United States", "United Kingdom", "Canada", "Australia", "Singapore", "Germany"]
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
DECIMAL_RE = re.compile(r"(?<![A-Z0-9])\d+\.\d{2}(?![A-Z0-9])")
DOC_NUM_RE = re.compile(r"\b(?:[A-Z]\d{7}|[A-Z]{2}\d{6}|\d{9})\b")
REFERENCE_RE = re.compile(r"\b(?:TRX-\d{6}|PMT-\d{8}|REF[A-Z0-9]{7})\b", re.IGNORECASE)
MONEY_RE = re.compile(r"(?:\b(?:USD|EUR|GBP)\b\s*)?[$€£]?\s*\d+(?:\.\d+)?(?:\s*\b(?:USD|EUR|GBP)\b)?")


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_label_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_value_text(text: str | None) -> str | None:
    if not text:
        return None
    value = re.sub(r"^[\s:\-–—]+", "", text).strip()
    value = re.sub(r"\s+", " ", value)
    return value or None


def _sort_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tokens, key=lambda token: (token["bbox"][0], token["bbox"][1], token["bbox"][2], token["bbox"][3]))


def _join_tokens(tokens: list[dict[str, Any]]) -> str:
    if not tokens:
        return ""
    ordered = _sort_tokens(tokens)
    parts = [ordered[0]["text"]]
    prev = ordered[0]
    for token in ordered[1:]:
        gap = token["bbox"][0] - prev["bbox"][2]
        prev_width = max(1, prev["bbox"][2] - prev["bbox"][0])
        token_width = max(1, token["bbox"][2] - token["bbox"][0])
        prev_char = prev_width / max(len(prev["text"]), 1)
        token_char = token_width / max(len(token["text"]), 1)
        join_without_space = gap <= max(2.0, min(prev_char, token_char) * 0.35)
        parts.append(token["text"] if join_without_space else f" {token['text']}")
        prev = token
    return "".join(parts).strip()


def _build_page_lines(ocr_data: dict[str, Any]) -> list[dict[str, Any]]:
    line_map: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for page in ocr_data.get("pages", []):
        for token in page.get("tokens", []):
            line_map[int(token["line_id"])].append(token)

    page_lines = []
    for line_id, raw_tokens in line_map.items():
        tokens = _sort_tokens(raw_tokens)
        block_id = Counter(int(token["block_id"]) for token in tokens).most_common(1)[0][0]
        page_lines.append(
            {
                "line_id": line_id,
                "block_id": block_id,
                "tokens": tokens,
                "text": _join_tokens(tokens),
                "x1": min(token["bbox"][0] for token in tokens),
                "y1": min(token["bbox"][1] for token in tokens),
                "x2": max(token["bbox"][2] for token in tokens),
                "y2": max(token["bbox"][3] for token in tokens),
            }
        )
    return sorted(page_lines, key=lambda line: (line["y1"], line["x1"], line["line_id"]))


def _build_blocks_from_ocr(ocr_data: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    block_line_map: dict[int, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for page in ocr_data.get("pages", []):
        for token in page.get("tokens", []):
            block_line_map[int(token["block_id"])][int(token["line_id"])].append(token)

    blocks: dict[int, list[dict[str, Any]]] = {}
    for block_id, line_map in block_line_map.items():
        block_lines = []
        for line_id, raw_tokens in line_map.items():
            tokens = _sort_tokens(raw_tokens)
            block_lines.append(
                {
                    "line_id": line_id,
                    "block_id": block_id,
                    "tokens": tokens,
                    "text": _join_tokens(tokens),
                    "x1": min(token["bbox"][0] for token in tokens),
                    "y1": min(token["bbox"][1] for token in tokens),
                    "x2": max(token["bbox"][2] for token in tokens),
                    "y2": max(token["bbox"][3] for token in tokens),
                }
            )
        blocks[block_id] = sorted(block_lines, key=lambda line: (line["y1"], line["x1"], line["line_id"]))
    return blocks


def _flatten_blocks(blocks: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    page_lines = []
    for block_lines in blocks.values():
        page_lines.extend(block_lines)
    return sorted(page_lines, key=lambda line: (line["y1"], line["x1"], line["block_id"], line["line_id"]))


def _label_score(prefix_norm: str, synonym_norm: str) -> float:
    ratio = fuzz.ratio(prefix_norm, synonym_norm)
    token_sort = fuzz.token_sort_ratio(prefix_norm, synonym_norm)
    word_penalty = abs(len(prefix_norm.split()) - len(synonym_norm.split())) * 3.0
    char_penalty = abs(len(prefix_norm) - len(synonym_norm)) * 0.15
    score = max(ratio, token_sort) - word_penalty - char_penalty
    if prefix_norm == synonym_norm:
        score += 20.0
    return score


def _remainder_is_label_fragment(remainder: str | None, synonym: str) -> bool:
    if not remainder:
        return True
    rem_norm = _normalize_label_text(remainder)
    syn_norm = _normalize_label_text(synonym)
    if not rem_norm:
        return True
    rem_tokens = rem_norm.split()
    syn_tokens = syn_norm.split()
    if rem_norm == syn_norm:
        return True
    if rem_tokens and set(rem_tokens).issubset(set(syn_tokens)):
        return True
    if len(rem_tokens) == 1 and rem_tokens[0] in syn_tokens:
        return True
    return False


def _best_prefix_match(tokens: list[dict[str, Any]], synonyms: list[str]) -> dict[str, Any] | None:
    texts = [token["text"] for token in tokens]
    best: dict[str, Any] | None = None
    for synonym in synonyms:
        synonym_norm = _normalize_label_text(synonym)
        syn_words = max(1, len(synonym_norm.split()))
        for prefix_len in range(1, min(len(texts), syn_words + 2) + 1):
            prefix_text = " ".join(texts[:prefix_len]).strip()
            prefix_norm = _normalize_label_text(prefix_text)
            if not prefix_norm:
                continue
            score = _label_score(prefix_norm, synonym_norm)
            if best is None or score > best["score"]:
                best = {
                    "score": score,
                    "prefix_len": prefix_len,
                    "rest": _clean_value_text(" ".join(texts[prefix_len:])),
                    "synonym": synonym,
                }
    return best


def _extract_from_blocks(blocks: dict[int, list[dict[str, Any]]], synonyms: list[str], threshold: float = 86.0) -> str | None:
    candidates: list[tuple[float, str]] = []
    for block_lines in blocks.values():
        for index, line in enumerate(block_lines):
            match = _best_prefix_match(line["tokens"], synonyms)
            if not match or match["score"] < threshold:
                continue
            prefix_text = " ".join(token["text"] for token in line["tokens"][: match["prefix_len"]])
            line_label_norm = _normalize_label_text(prefix_text)
            synonym_norm = _normalize_label_text(match["synonym"])
            if line_label_norm != synonym_norm and fuzz.ratio(line_label_norm, synonym_norm) < 85:
                continue
            value = match["rest"]
            if _remainder_is_label_fragment(value, match["synonym"]):
                value = None
            if not value:
                for next_line in block_lines[index + 1 :]:
                    next_text = _clean_value_text(next_line["text"])
                    if next_text:
                        value = next_text
                        break
            if value:
                candidates.append((match["score"] + min(len(value), 30) * 0.1, value))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _collect_pattern_matches(page_lines: list[dict[str, Any]], pattern: re.Pattern[str], field_name: str) -> list[str]:
    values = []
    for line in page_lines:
        if "<" in line["text"]:
            continue
        for match in pattern.findall(line["text"]):
            canonical = canonicalize_value(field_name, match)
            if canonical is not None:
                values.append(canonical)
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _collect_dates(page_lines: list[dict[str, Any]]) -> list[datetime]:
    parsed = []
    for value in _collect_pattern_matches(page_lines, DATE_RE, "date_of_birth"):
        try:
            parsed.append(datetime.strptime(value, "%Y-%m-%d"))
        except ValueError:
            continue
    unique = []
    seen = set()
    for item in parsed:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return sorted(unique)


def _pick_gov_dates(page_lines: list[dict[str, Any]], fields: dict[str, Any]) -> None:
    dates = _collect_dates(page_lines)
    if len(dates) < 3:
        return
    for i in range(len(dates)):
        for j in range(len(dates)):
            for k in range(len(dates)):
                if len({i, j, k}) < 3:
                    continue
                dob = dates[i]
                issue = dates[j]
                expiry = dates[k]
                age_years = issue.year - dob.year - ((issue.month, issue.day) < (dob.month, dob.day))
                expiry_years = expiry.year - issue.year
                if age_years >= 18 and expiry_years in {5, 10} and (expiry.month, expiry.day) == (issue.month, issue.day):
                    fields["date_of_birth"] = dob.strftime("%Y-%m-%d")
                    fields["issue_date"] = issue.strftime("%Y-%m-%d")
                    fields["expiry_date"] = expiry.strftime("%Y-%m-%d")
                    return


def _collect_country(page_lines: list[dict[str, Any]]) -> str | None:
    joined = "\n".join(line["text"] for line in page_lines)
    for country in KNOWN_COUNTRIES:
        if country.lower() in joined.lower():
            return country
    return None


def _collect_name_candidates(page_lines: list[dict[str, Any]]) -> list[str]:
    candidates = []
    for line in page_lines:
        text = _clean_value_text(line["text"])
        if not text:
            continue
        if any(ch.isdigit() for ch in text) or "[PHOTO]" in text or "<" in text:
            continue
        words = text.split()
        if not (2 <= len(words) <= 4):
            continue
        if any(word.lower() in {"passport", "identity", "date", "issue", "expiry", "country", "amount", "from", "to", "reference", "statement", "address", "bill"} for word in words):
            continue
        candidates.append(text)
    return candidates


def _extract_government_id(page_lines: list[dict[str, Any]], blocks: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    fields = {}
    for field_name, synonyms in LABELS["government_id"].items():
        fields[field_name] = _extract_from_blocks(blocks, synonyms, threshold=84.0)

    if not fields.get("document_number"):
        matches = _collect_pattern_matches(page_lines, DOC_NUM_RE, "document_number")
        if matches:
            fields["document_number"] = matches[0]

    _pick_gov_dates(page_lines, fields)

    if not fields.get("issuing_country"):
        fields["issuing_country"] = _collect_country(page_lines)

    full_name = fields.get("full_name")
    if not full_name or len(str(full_name).split()) < 2:
        name_candidates = _collect_name_candidates(page_lines[:10])
        if name_candidates:
            fields["full_name"] = name_candidates[0]

    return fields


def _extract_payment_receipt(page_lines: list[dict[str, Any]], blocks: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    fields = {}
    for field_name in ["sender_name", "recipient_name", "payment_date", "reference_id", "currency"]:
        threshold = 88.0 if field_name == "currency" else 84.0
        fields[field_name] = _extract_from_blocks(blocks, LABELS["payment_receipt"][field_name], threshold=threshold)

    if not fields.get("sender_name"):
        from_value = _extract_from_blocks(blocks, LABELS["payment_receipt"]["sender_name"], threshold=80.0)
        fields["sender_name"] = from_value
    if not fields.get("recipient_name"):
        to_value = _extract_from_blocks(blocks, LABELS["payment_receipt"]["recipient_name"], threshold=80.0)
        fields["recipient_name"] = to_value

    if not fields.get("reference_id"):
        matches = _collect_pattern_matches(page_lines, REFERENCE_RE, "reference_id")
        if matches:
            fields["reference_id"] = matches[0]

    if not fields.get("payment_date"):
        dates = _collect_pattern_matches(page_lines, DATE_RE, "payment_date")
        if dates:
            fields["payment_date"] = dates[0]

    amount_candidates = []
    labeled_amount = _extract_from_blocks(blocks, LABELS["payment_receipt"]["amount"], threshold=82.0)
    if labeled_amount:
        amount_candidates.append(labeled_amount)
    for line in page_lines:
        if re.search(r"subtotal|fee|tax|invoice|auth|reference|transaction\s+id", line["text"], re.IGNORECASE):
            continue
        for match in DECIMAL_RE.findall(line["text"]):
            canonical = canonicalize_value("amount", match)
            if canonical is not None:
                amount_candidates.append(canonical)
    normalized_amounts = []
    for value in amount_candidates:
        canonical = canonicalize_value("amount", value)
        if canonical is None:
            continue
        try:
            numeric_value = float(canonical)
        except (TypeError, ValueError):
            continue
        normalized_amounts.append((numeric_value, canonical))
    if normalized_amounts:
        normalized_amounts.sort(key=lambda item: item[0], reverse=True)
        fields["amount"] = normalized_amounts[0][1]
    else:
        fields["amount"] = None

    if not fields.get("currency"):
        for line in page_lines:
            if fields.get("amount") and fields["amount"] in line["text"]:
                match = re.search(r"\b(?:USD|EUR|GBP)\b|[$€£]", line["text"])
                if match:
                    fields["currency"] = match.group(0)
                    break
        if not fields.get("currency"):
            for line in page_lines:
                match = re.search(r"\b(?:USD|EUR|GBP)\b|[$€£]", line["text"])
                if match:
                    fields["currency"] = match.group(0)
                    break

    return fields


def _find_best_anchor(page_lines: list[dict[str, Any]]) -> int | None:
    best_index = None
    best_score = 0.0
    for index, line in enumerate(page_lines):
        line_norm = _normalize_label_text(line["text"])
        if not line_norm:
            continue
        for anchor in POA_ANCHORS:
            score = _label_score(line_norm, _normalize_label_text(anchor))
            if score > best_score:
                best_score = score
                best_index = index
    if best_score >= 80.0:
        return best_index
    return None


def _parse_city_postal(text: str | None) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    if "," in text:
        city, postal = text.split(",", 1)
        return city.strip() or None, postal.strip() or None
    parts = text.rsplit(" ", 1)
    if len(parts) == 2:
        return parts[0].strip() or None, parts[1].strip() or None
    return text.strip() or None, None


def _extract_proof_of_address(page_lines: list[dict[str, Any]], blocks: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    fields = {field_name: None for field_name in SCHEMA_FIELDS["proof_of_address"]}

    if blocks:
        top_block_id = min(blocks, key=lambda block_id: blocks[block_id][0]["y1"])
        if blocks[top_block_id]:
            fields["issuer_name"] = _clean_value_text(blocks[top_block_id][0]["text"])

    fields["statement_date"] = _extract_from_blocks(blocks, LABELS["proof_of_address"]["statement_date"], threshold=90.0)
    if not fields.get("statement_date"):
        candidate_dates = []
        for line in page_lines:
            if re.search(r"statement|bill\s+date|issued\s+on", line["text"], re.IGNORECASE):
                candidate_dates.extend(_collect_pattern_matches([line], DATE_RE, "statement_date"))
        if candidate_dates:
            fields["statement_date"] = candidate_dates[0]

    anchor_index = _find_best_anchor(page_lines)
    if anchor_index is None:
        return fields

    anchor_line = page_lines[anchor_index]
    anchor_block_id = anchor_line["block_id"]
    candidate_lines = []
    for block_line in blocks.get(anchor_block_id, []):
        if block_line["line_id"] > anchor_line["line_id"]:
            candidate_lines.append(block_line)
    if len(candidate_lines) < 4:
        for line in page_lines[anchor_index + 1 :]:
            if line["y1"] <= anchor_line["y1"]:
                continue
            if abs(line["x1"] - anchor_line["x1"]) <= 260:
                candidate_lines.append(line)
            if len(candidate_lines) >= 4:
                break

    deduped = []
    seen_line_ids = set()
    for line in candidate_lines:
        if line["line_id"] in seen_line_ids:
            continue
        deduped.append(line)
        seen_line_ids.add(line["line_id"])
    candidate_lines = deduped[:4]

    if len(candidate_lines) >= 1:
        fields["full_name"] = _clean_value_text(candidate_lines[0]["text"])
    if len(candidate_lines) >= 2:
        fields["address_line1"] = _clean_value_text(candidate_lines[1]["text"])
    if len(candidate_lines) >= 3:
        fields["city"], fields["postal_code"] = _parse_city_postal(_clean_value_text(candidate_lines[2]["text"]))
    if len(candidate_lines) >= 4:
        fields["country"] = _clean_value_text(candidate_lines[3]["text"])

    return fields


def _canonicalize_fields(schema_name: str, fields: dict[str, Any]) -> dict[str, Any]:
    return {
        field_name: canonicalize_value(field_name, fields.get(field_name))
        for field_name in SCHEMA_FIELDS[schema_name]
    }


def predict(document_dir: str) -> dict:
    meta = _load_json(os.path.join(document_dir, "meta.json"))
    ocr_data = _load_json(os.path.join(document_dir, "ocr.json"))
    schema_name = meta["schema_name"]

    page_lines = _build_page_lines(ocr_data)
    blocks = _build_blocks_from_ocr(ocr_data)
    page_lines = _flatten_blocks(blocks)

    if schema_name == "government_id":
        fields = _extract_government_id(page_lines, blocks)
    elif schema_name == "proof_of_address":
        fields = _extract_proof_of_address(page_lines, blocks)
    elif schema_name == "payment_receipt":
        fields = _extract_payment_receipt(page_lines, blocks)
    else:
        fields = {field_name: None for field_name in SCHEMA_FIELDS.get(schema_name, [])}

    return {
        "schema_name": schema_name,
        "fields": _canonicalize_fields(schema_name, fields),
    }

"""Comparable OCR extraction adapters; these functions never read model gold.

The NER adapter is a separate entity-to-fields pipeline. Swarm uses two
samples of the same model and a merger, not three independently trained models.
The runner records upstream traffic separately to audit reported usage/calls.
"""
from __future__ import annotations

import json
from http.client import HTTPException
import math
from pathlib import Path
import re
import statistics
import time
from typing import Any, Literal
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .experiments import (
    DIRECT_PROMPT, MAX_RESPONSE_BYTES, ocr_view, parse_prediction, strict_json,
    validate_endpoint, write_json,
)
from .schemas import SCHEMA_NAMES, field_names, load_schema, validate_prediction

Method = Literal["heuristic", "direct", "swarm", "ner"]
METHODS = ("heuristic", "direct", "swarm", "ner")
TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")
MAX_TEXT_CHARACTERS = 32_000

# Descriptions assign document roles rather than generic PERSON/ADDRESS labels.
ROLE_DESCRIPTIONS = {
    "government_id": {
        "full_name": "Full name of the identity document holder, excluding titles and field labels.",
        "date_of_birth": "The holder's date of birth, not an issue or expiry date.",
        "document_number": "The complete identity document number, not a partial personal number.",
        "issue_date": "Date this identity document was issued, not birth or expiry date.",
        "expiry_date": "Expiry date of this identity document.",
        "issuing_country": "Country issuing the identity document, not a place of birth.",
    },
    "proof_of_address": {
        "full_name": "The customer or account holder's full name, not the issuer or provider.",
        "address_line1": "First street address line of the customer, not the issuer's address.",
        "city": "City in the customer's address, not the issuer's city.",
        "postal_code": "Postal or ZIP code of the customer, not the issuer's postal code.",
        "country": "Country in the customer's address, not the issuer's country.",
        "statement_date": "Date the statement was issued, not its payment due date.",
        "issuer_name": "Organization issuing the statement or bill, not the customer.",
    },
    "payment_receipt": {
        "sender_name": "The payer or sender making this payment, not its recipient or merchant.",
        "recipient_name": "The payee, recipient or merchant receiving this payment, not the payer.",
        "amount": "Total amount actually paid, excluding a fee, tax or subtotal alone.",
        "currency": "Currency code or currency symbol for the payment amount.",
        "payment_date": "Date of this payment or transaction.",
        "reference_id": "Payment transaction reference, not an invoice number or authorization code.",
    },
}


def ocr_text(ocr: dict[str, Any]) -> str:
    """The same text and geometry for every model pipeline, with no correction."""
    return "\n".join(
        f"[page={line['page']} block={line['block']} line={line['line']} "
        f"x={line['x']} y={line['y']}] {line['text']}"
        for line in ocr_view(ocr)
    )


def build_request(
    method: Method, schema_name: str, text: str, *, model: str | None = None,
    prompt: str = DIRECT_PROMPT, max_tokens: int = 512,
) -> dict[str, Any]:
    """Return the exact request body, also usable in the protocol freeze."""
    if method not in METHODS:
        raise ValueError("Unknown comparison method")
    names = field_names(schema_name)
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARACTERS:
        raise ValueError("OCR text must contain 1 to 32000 characters")
    text.encode("utf-8")
    if type(max_tokens) is not int or not 1 <= max_tokens <= 16384:
        raise ValueError("max_tokens must be an integer from 1 to 16384")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise ValueError("Prompt must contain 1 to 20000 characters")
    prompt.encode("utf-8")
    if method == "heuristic":
        return {}
    if not isinstance(model, str) or not model.strip() or len(model) > 128:
        raise ValueError("A model name of 1 to 128 characters is required")
    if method == "ner":
        return {
            "text": text,
            "config": {
                "labels": [{"name": name.upper(), "description": ROLE_DESCRIPTIONS[schema_name][name]}
                           for name in names],
                "model": model, "require_offsets": True, "case_sensitive": True,
                "retries": 1, "max_tokens": max_tokens,
            },
        }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({
                "schema_name": schema_name, "required_fields": list(names), "ocr_text": text,
            }, ensure_ascii=False)},
        ],
        "max_tokens": max_tokens, "stream": False, "seed": 17,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": load_schema(schema_name)},
        },
    }
    # Swarm's request-level options override generator configuration. Omitting
    # temperature keeps the deliberately different configured sampling values.
    if method == "direct":
        body["temperature"] = 0
    return body


def _usage(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("usage must be an object or null")
    for key in TOKEN_KEYS:
        if key in value and (type(value[key]) is not int or value[key] < 0):
            raise ValueError("Token counts must be nonnegative integers")
    result = {key: value[key] for key in TOKEN_KEYS if key in value}
    if len(result) == 3 and result["total_tokens"] != result["prompt_tokens"] + result["completion_tokens"]:
        raise ValueError("Inconsistent aggregate token usage")
    return result or None


def ner_prediction(schema_name: str, text: str, entities: Any) -> tuple[dict[str, Any], list[str]]:
    """Ground spans and map unique role values; conflicting roles abstain.

    Only the scorer applies the repository's common canonicalization. This
    adapter never repairs OCR, infers absent values, or chooses from gold.
    """
    names = field_names(schema_name)
    labels = {name.upper(): name for name in names}
    if not isinstance(entities, list) or len(entities) > 2048:
        raise ValueError("Invalid entity list")
    candidates: dict[str, set[str]] = {name: set() for name in names}
    intervals = []
    for entity in entities:
        if not isinstance(entity, dict) or set(entity) != {"text", "label", "start", "end"}:
            raise ValueError("Invalid entity shape")
        surface, label, start, end = (entity[k] for k in ("text", "label", "start", "end"))
        if not isinstance(label, str) or label not in labels:
            raise ValueError("Unknown entity label")
        if not isinstance(surface, str) or not surface or len(surface) > MAX_TEXT_CHARACTERS:
            raise ValueError("Invalid entity text")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise ValueError("Invalid entity offsets")
        if text[start:end] != surface:
            raise ValueError("Entity does not match the source text")
        if any(start < previous_end and previous_start < end for previous_start, previous_end in intervals):
            raise ValueError("Overlapping entity offsets violate the NER contract")
        intervals.append((start, end))
        candidates[labels[label]].add(surface)
    conflicts = [name for name, values in candidates.items() if len(values) > 1]
    fields = {name: next(iter(values)) if len(values) == 1 else None
              for name, values in candidates.items()}
    return {"schema_name": schema_name, "fields": fields}, conflicts


def _parse_chat(method: str, schema_name: str, response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise ValueError("Chat response must be an object")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ValueError("Expected exactly one completion choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ValueError("Expected an assistant message")
    content, reason = message.get("content"), choice.get("finish_reason")
    if not isinstance(content, str) or not isinstance(reason, str):
        raise ValueError("Expected text content and a finish reason")
    result = {"content": content, "finish_reason": reason,
              "usage": _usage(response.get("usage")), "calls": 1,
              "model": response.get("model")}
    if reason not in {"stop", "length"} or message.get("tool_calls") or message.get("refusal"):
        result["record"] = {"status": "invalid_prediction"}
        result["error"] = "unexpected_completion"
    else:
        parsed = parse_prediction(content, schema_name, reason)
        result["record"] = {k: v for k, v in parsed.items() if k != "error"}
        if "error" in parsed:
            result["error"] = parsed["error"]
    if method == "swarm":
        swarm = response.get("swarm")
        if not isinstance(swarm, dict) or not isinstance(swarm.get("calls"), list):
            raise ValueError("Swarm response must include actual call metadata")
        if type(swarm.get("degraded")) is not bool or type(swarm.get("usage_complete")) is not bool:
            raise ValueError("Invalid Swarm completion flags")
        calls = swarm["calls"]
        if not 1 <= len(calls) <= 32:
            raise ValueError("Invalid Swarm call count")
        for call in calls:
            if not isinstance(call, dict) or not all(isinstance(call.get(k), str)
                                                     for k in ("stage", "provider", "model", "status")):
                raise ValueError("Invalid Swarm call metadata")
            _usage(call.get("usage"))
        result.update(calls=len(calls), swarm=swarm)
        if swarm["usage_complete"]:
            if result["usage"] is None or any(_usage(c.get("usage")) is None for c in calls):
                raise ValueError("Swarm claims complete usage without token counts")
            for key in TOKEN_KEYS:
                if key not in result["usage"] or any(key not in (_usage(c.get("usage")) or {}) for c in calls):
                    raise ValueError("Swarm complete usage requires all token counters")
                if result["usage"][key] != sum(c["usage"][key] for c in calls):
                    raise ValueError("Swarm aggregate usage differs from its call trace")
        elif result["usage"] is not None:
            raise ValueError("Swarm reports aggregate usage despite incomplete calls")
    return result


def _parse_ner(schema_name: str, text: str, response: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or not isinstance(response.get("data"), dict):
        raise ValueError("Invalid NER response envelope")
    data, meta = response["data"], response.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("Missing NER response metadata")
    attempts, cache_hit = meta.get("attempts"), meta.get("cache_hit")
    if type(attempts) is not int or attempts < 0 or type(cache_hit) is not bool:
        raise ValueError("Invalid NER attempt metadata")
    if (cache_hit and attempts != 0) or (not cache_hit and attempts != 1):
        raise ValueError("NER attempts violate the one-call protocol")
    if cache_hit:
        raise ValueError("NER cache must be disabled for comparison")
    prediction, conflicts = ner_prediction(schema_name, text, data.get("entities"))
    warnings = meta.get("warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(w, str) for w in warnings):
        raise ValueError("Invalid NER warnings")
    return {"record": {"status": "ok", "prediction": prediction},
            "usage": _usage(data.get("usage")), "calls": attempts,
            "model": data.get("model"), "provider": data.get("provider"),
            "conflicting_fields": conflicts, "warnings": warnings, "ner_meta": meta}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _redact(value: Any, api_key: str | None) -> Any:
    if not api_key:
        return value
    if isinstance(value, str):
        return value.replace(api_key, "[redacted]")
    if isinstance(value, list):
        return [_redact(item, api_key) for item in value]
    if isinstance(value, dict):
        return {_redact(key, api_key): _redact(item, api_key) for key, item in value.items()}
    return value


def _check_tree(value: Any) -> None:
    """Bound nesting before retaining or recursively sanitizing provider JSON."""
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 64 or count > 100_000:
            raise ValueError("Provider JSON structure exceeds bounds")
        if isinstance(item, dict):
            for key in item:
                key.encode("utf-8")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            item.encode("utf-8")


def infer_document(
    method: Method, schema_name: str, text: str, *, endpoint: str | None = None,
    model: str | None = None, prompt: str = DIRECT_PROMPT, max_tokens: int = 512,
    timeout: float = 180, api_key: str | None = None, trace_id: str | None = None,
    document_dir: Path | None = None,
) -> dict[str, Any]:
    """Return a frozen prediction record and transport evidence, even on failure.

    Invalid local configuration raises before making any request. Endpoint
    failures become explicit failed records so a fixed dataset is never trimmed.
    """
    body = build_request(method, schema_name, text, model=model, prompt=prompt, max_tokens=max_tokens)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive and finite")
    if trace_id is not None and (not isinstance(trace_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", trace_id)):
        raise ValueError("Invalid trace identifier")
    result: dict[str, Any] = {"method": method, "record": {"status": "runtime_exception"},
                              "usage": None, "calls": None, "trace_id": trace_id,
                              "request_body": body, "raw_response": None}
    if method == "heuristic":
        if document_dir is None:
            raise ValueError("The unchanged heuristic requires its OCR document directory")
        from baselines.heuristic_baseline.extract import predict
        started = time.perf_counter()
        try:
            prediction = predict(str(document_dir))
            if not validate_prediction(schema_name, prediction):
                raise ValueError("Invalid heuristic prediction")
            result.update(record={"status": "ok", "prediction": prediction},
                          raw_response=prediction, usage={key: 0 for key in TOKEN_KEYS}, calls=0)
        except (OSError, ValueError, KeyError, IndexError, TypeError, RecursionError) as exc:
            result.update(error="heuristic_error", error_type=type(exc).__name__, calls=0)
        result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
        return result
    if endpoint is None:
        raise ValueError("An endpoint is required for model inference")
    validate_endpoint(endpoint)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if trace_id:
        headers["X-KYC-Trace-ID"] = trace_id
    request = Request(endpoint, data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode(), headers=headers)
    started = time.perf_counter()
    try:
        try:
            response = build_opener(_NoRedirect()).open(request, timeout=timeout)
        except HTTPError as error:
            response = error
        with response:
            result["http_status"] = response.status
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            result.update(error="oversized_response", raw_response={"truncated": True,
                          "prefix": raw[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")})
            return result
        result["raw_response"] = {"raw_text": raw.decode("utf-8", errors="replace")}
        parsed = strict_json(raw.decode("utf-8"))
        _check_tree(parsed)
        result["raw_response"] = parsed
        if not 200 <= result["http_status"] < 300:
            result.update(error="http_error")
            return result
        result.update(_parse_ner(schema_name, text, parsed) if method == "ner"
                      else _parse_chat(method, schema_name, parsed))
    except (OSError, HTTPException, ValueError, KeyError, IndexError, TypeError, RecursionError) as exc:
        result.update(error="transport_error" if isinstance(exc, (OSError, HTTPException)) else "invalid_service_response",
                      error_type=type(exc).__name__)
    finally:
        result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
        # Credentials are never captured in request headers; redact a provider
        # that echoes an explicitly supplied secret in its response as well.
        if api_key:
            sanitized = _redact(result, api_key)
            result.clear()
            result.update(sanitized)
    return result


def summarize_comparison(dataset: Path, run: Path) -> dict[str, Any]:
    """Score frozen records using the trusted scorer, then report measured cost."""
    from .evaluation import evaluate_predictions
    from .prediction_io import load_prediction_file
    from task.tools.canonicalize import canonicalize_prediction

    manifest = strict_json((dataset / "manifest.json").read_text())
    docs = manifest["documents"]
    ids = {d["doc_id"] for d in docs}
    if not docs or len(ids) != len(docs):
        raise ValueError("Dataset must have nonempty unique document identifiers")
    predictions = load_prediction_file(run / "predictions.json", ids)["documents"]
    if set(predictions) != ids:
        raise ValueError("Prediction identifiers differ from the frozen dataset")
    traces = [strict_json(line) for line in (run / "traces.jsonl").read_text().splitlines()]
    if len(traces) != len(ids) or {t.get("doc_id") for t in traces} != ids:
        raise ValueError("Exactly one trace per frozen document is required")
    trusted = evaluate_predictions(predictions, dataset / "inputs", dataset / "gold", include_error_summary=True)
    rows = []
    for doc in docs:
        record = predictions[doc["doc_id"]]
        trace = next(t for t in traces if t["doc_id"] == doc["doc_id"])
        if trace.get("record") != record:
            raise ValueError("Trace record differs from its frozen prediction")
        gold = canonicalize_prediction(strict_json((dataset / "gold" / f"{doc['doc_id']}.json").read_text()))["fields"]
        valid = record["status"] == "ok" and validate_prediction(doc["schema_name"], record.get("prediction"))
        got = canonicalize_prediction(record["prediction"])["fields"] if valid else {}
        errors = {name: {"expected": value, "predicted": got.get(name)}
                  for name, value in gold.items() if not valid or got.get(name) != value}
        rows.append({**doc, "status": record["status"], "num_fields": len(gold),
                     "correct_fields": len(gold) - len(errors), "exact_doc": not errors,
                     "null_fields": sum(value is None for value in gold.values()),
                     "correct_nulls": sum(valid and value is None and got.get(name) is None
                                          for name, value in gold.items()),
                     "hallucinated_nulls": sum(valid and value is None and got.get(name) is not None
                                               for name, value in gold.items()),
                     "errors": errors})

    def metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
        fields = sum(r["num_fields"] for r in items)
        correct = sum(r["correct_fields"] for r in items)
        return {"num_docs": len(items), "correct_fields": correct, "total_fields": fields,
                "field_accuracy": round(correct / fields, 6) if fields else None,
                "exact_docs": sum(r["exact_doc"] for r in items),
                "null_fields": sum(r["null_fields"] for r in items),
                "correct_nulls": sum(r["correct_nulls"] for r in items),
                "hallucinated_nulls": sum(r["hallucinated_nulls"] for r in items)}

    latency = [t["elapsed_seconds"] for t in traces]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in latency):
        raise ValueError("Every trace requires a nonnegative finite duration")
    usage = [_usage(t.get("usage")) for t in traces]
    usage_complete = all(value is not None and all(k in value for k in TOKEN_KEYS) for value in usage)
    tokens = {key: sum((u or {}).get(key, 0) for u in usage) if usage_complete else None for key in TOKEN_KEYS}
    reported = [t.get("calls") for t in traces]
    if any(v is not None and (type(v) is not int or v < 0) for v in reported):
        raise ValueError("Reported call counts must be nonnegative integers or null")
    # The runner attaches an independently observed proxy count per serial
    # request. Missing observations remain unknown, never silently zero.
    observed = [t.get("observed_calls") for t in traces]
    if any(v is not None and (type(v) is not int or v < 0) for v in observed):
        raise ValueError("Observed call counts must be nonnegative integers or null")
    observed_usage = [_usage(t.get("observed_usage")) if t.get("observed_usage_complete") is True else None
                      for t in traces]
    observed_usage_complete = all(u is not None and all(k in u for k in TOKEN_KEYS) for u in observed_usage)
    observed_truncations = [t.get("observed_truncated_responses") for t in traces]
    if any(v is not None and (type(v) is not int or v < 0) for v in observed_truncations):
        raise ValueError("Observed truncation counts must be nonnegative integers or null")
    paired = []
    for base in sorted({r["base_id"] for r in rows if "base_id" in r}):
        values = {r["ocr_profile"]: r for r in rows if r.get("base_id") == base}
        if "clean" in values and "standard_noise" in values:
            clean, noisy = values["clean"], values["standard_noise"]
            paired.append({"base_id": base, "schema_name": clean["schema_name"],
                           "clean_correct_fields": clean["correct_fields"],
                           "noisy_correct_fields": noisy["correct_fields"],
                           "field_accuracy_delta": round((noisy["correct_fields"] - clean["correct_fields"]) / clean["num_fields"], 6)})
    result = {
        **metrics(rows), "official_score": trusted,
        "by_schema": {key: metrics([r for r in rows if r["schema_name"] == key]) for key in SCHEMA_NAMES},
        "by_ocr_profile": {key: metrics([r for r in rows if r["ocr_profile"] == key])
                           for key in sorted({r["ocr_profile"] for r in rows})},
        "by_template": {key: metrics([r for r in rows if r.get("template") == key])
                        for key in sorted({r["template"] for r in rows if "template" in r})},
        "paired_ocr": paired, "independent_base_documents": len({r.get("base_id", r["doc_id"]) for r in rows}),
        "invalid_predictions": sum(t["record"]["status"] != "ok" for t in traces),
        "invalid_json": sum(t.get("error") == "invalid_json" for t in traces),
        "truncated_responses": sum(t.get("finish_reason") == "length" for t in traces),
        "observed_truncated_responses": sum(observed_truncations)
            if all(v is not None for v in observed_truncations) else None,
        "errors": {key: sum(t.get("error") == key for t in traces)
                   for key in sorted({t["error"] for t in traces if "error" in t})},
        "latency_seconds": {"total": round(sum(latency), 6), "mean": round(statistics.mean(latency), 6),
                            "median": round(statistics.median(latency), 6),
                            "p95": sorted(latency)[math.ceil(len(latency) * .95) - 1]},
        "tokens": tokens, "usage_complete": usage_complete,
        "known_tokens": {key: sum((u or {}).get(key, 0) for u in usage) for key in TOKEN_KEYS},
        "observed_tokens": {key: sum(u[key] for u in observed_usage) if observed_usage_complete else None
                            for key in TOKEN_KEYS},
        "observed_usage_complete": observed_usage_complete,
        "token_mismatched_documents": [t["doc_id"] for t, a, b in zip(traces, usage, observed_usage)
                                       if a is not None and b is not None and a != b],
        "calls": {"reported": sum(reported) if all(v is not None for v in reported) else None,
                  "observed": sum(observed) if all(v is not None for v in observed) else None,
                  "known_reported": sum(v for v in reported if v is not None),
                  "known_observed": sum(v for v in observed if v is not None),
                  "mismatched_documents": [t["doc_id"] for t, a, b in zip(traces, reported, observed)
                                           if a is not None and b is not None and a != b]},
        "currency_cost": None, "documents": rows,
    }
    write_json(run / "metrics.json", result)
    return result

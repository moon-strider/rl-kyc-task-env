"""Compare real extraction pipelines, then select prompts using development data only.

Run from a checkout with the local model and the NER/Swarm checkouts installed.
All documents are synthetic. No weights are trained and no cloud key is required.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from comparison_stack import ComparisonStack
from rl_kyc_task_env.comparison import (
    DIRECT_PROMPT, METHODS, TOKEN_KEYS, build_request, infer_document,
    ocr_text, summarize_comparison,
)
from rl_kyc_task_env.comparison_dataset import generate_split, protocol as dataset_protocol
from rl_kyc_task_env.experiments import chat, strict_json, write_json
from rl_kyc_task_env.schemas import SCHEMA_NAMES
from task.tools.canonicalize import canonicalize_prediction

ROOT = Path(__file__).resolve().parents[1]
MAX_TOKENS = 512
REFLECTION_TOKENS = 768


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes() -> dict[str, str]:
    files = {ROOT / "pyproject.toml", ROOT / "uv.lock"}
    for directory in ["scripts", "rl_kyc_task_env", "generator", "baselines", "task/tools", "judge"]:
        files.update((ROOT / directory).rglob("*.py"))
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted(files)}


def observation(stack: ComparisonStack, mark: int, trace_id: str) -> dict:
    records = [
        item for item in stack.traces_since(mark)
        if item["method"] == "POST" and item["path"].endswith("/chat/completions")
    ]
    if any(item["trace_id"] != trace_id for item in records):
        raise RuntimeError("Upstream trace attribution crossed document boundaries")
    usage = [item.get("response", {}).get("usage") if isinstance(item.get("response"), dict)
             else None for item in records]
    complete = all(
        isinstance(value, dict) and all(type(value.get(k)) is int and value[k] >= 0
                                       for k in TOKEN_KEYS)
        for value in usage
    )
    return {
        "observed_calls": len(records),
        "upstream_call_ids": [item["call_id"] for item in records],
        "observed_usage_complete": complete,
        "observed_usage": {
            key: sum(value[key] for value in usage) if complete else None for key in TOKEN_KEYS
        },
        "upstream_errors": [item["call_id"] for item in records
                            if item.get("upstream_status") != 200 or item.get("error")],
        "observed_truncated_responses": sum(
            any(choice.get("finish_reason") == "length" for choice in item["response"].get("choices", [])
                if isinstance(choice, dict))
            for item in records if isinstance(item.get("response"), dict)
        ),
    }


def endpoint(stack: ComparisonStack, method: str) -> tuple[str | None, str | None]:
    return {
        "heuristic": (None, None),
        "direct": (stack.direct_endpoint, stack.model),
        "ner": (stack.ner_endpoint, stack.model),
        "swarm": (stack.swarm_endpoint, stack.swarm_model),
    }[method]


def run_method(stack: ComparisonStack, dataset: Path, output: Path,
               method: str, prompt: str) -> dict:
    output.mkdir()
    (output / "prompt.txt").write_text(prompt + "\n")
    url, model = endpoint(stack, method)
    write_json(output / "settings.json", {
        "method": method, "model": model, "endpoint": url, "max_tokens": MAX_TOKENS,
        "prompt_sha256": digest(output / "prompt.txt"), "started_at_utc": now(),
    })
    manifest = strict_json((dataset / "manifest.json").read_text())
    predictions = {}
    with (output / "traces.jsonl").open("w") as handle:
        for item in manifest["documents"]:
            doc_id, schema = item["doc_id"], item["schema_name"]
            directory = dataset / "inputs" / doc_id
            text = ocr_text(strict_json((directory / "ocr.json").read_text()))
            trace_id = f"{output.name}:{doc_id}"
            mark = stack.mark()
            stack.set_trace_id(trace_id)
            try:
                result = infer_document(
                    method, schema, text, endpoint=url, model=model, prompt=prompt,
                    max_tokens=MAX_TOKENS, timeout=660 if method == "swarm" else 330,
                    trace_id=trace_id, document_dir=directory,
                )
                result.update(observation(stack, mark, trace_id))
            finally:
                stack.set_trace_id(None)
            record = {key: value for key, value in result["record"].items()
                      if key in {"status", "prediction"}}
            if "error" in result["record"] and "error" not in result:
                result["error"] = result["record"]["error"]
            result.update(doc_id=doc_id, schema_name=schema, record=record,
                          ocr_sha256=digest(directory / "ocr.json"))
            predictions[doc_id] = record
            handle.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
            handle.flush()
            write_json(output / "predictions.json", {"version": 1, "documents": predictions})
            print(json.dumps({
                "run": output.name, "document": doc_id, "status": record["status"],
                "seconds": result["elapsed_seconds"], "calls": result["observed_calls"],
            }), flush=True)
    metrics = summarize_comparison(dataset, output)
    print(json.dumps({
        "run": output.name, "score": metrics["official_score"]["score"],
        "correct_fields": metrics["correct_fields"], "fields": metrics["total_fields"],
        "invalid": metrics["invalid_predictions"],
    }), flush=True)
    return metrics


def preflight(stack: ComparisonStack, output: Path) -> bool:
    """A fixed toy receipt checks real APIs before freezing experimental data."""
    text = (
        "SYNTHETIC TEST RECEIPT\nSender: Avery Example\nRecipient: Riley Sample\n"
        "Amount: 125.50\nCurrency: USD\nPayment date: 2026-09-01\nReference: DEMO-4927\n"
    )
    expected = {"schema_name": "payment_receipt", "fields": {
        "sender_name": "Avery Example", "recipient_name": "Riley Sample",
        "amount": "125.50", "currency": "USD", "payment_date": "2026-09-01",
        "reference_id": "DEMO-4927",
    }}
    results = {}
    for method in ["direct", "swarm", "ner"]:
        url, model = endpoint(stack, method)
        trace_id = f"preflight:{method}"
        mark = stack.mark()
        stack.set_trace_id(trace_id)
        try:
            result = infer_document(
                method, "payment_receipt", text, endpoint=url, model=model,
                timeout=660 if method == "swarm" else 330, trace_id=trace_id,
            )
            result.update(observation(stack, mark, trace_id))
        finally:
            stack.set_trace_id(None)
        record = result["record"]
        result["exact_canary"] = (
            record["status"] == "ok"
            and canonicalize_prediction(record["prediction"]) == canonicalize_prediction(expected)
        )
        results[method] = result
        write_json(output / "preflight.json", {
            "synthetic": True, "input": text, "expected": expected, "methods": results,
        })
        print(json.dumps({"preflight": method, "status": record["status"],
                          "exact": result["exact_canary"], "calls": result["observed_calls"]}),
              flush=True)
    return all(result["exact_canary"] for result in results.values())


def reflect(stack: ComparisonStack, dev: Path, current: dict, current_prompt: str,
            output: Path, round_number: int, history: list[dict]) -> str | None:
    output.mkdir()
    manifest = strict_json((dev / "manifest.json").read_text())
    if manifest["split"] != "dev":
        raise ValueError("Reflection requires development data")
    # Predetermined feedback budget: at most one error document per schema.
    feedback = []
    for schema in SCHEMA_NAMES:
        rows = sorted(
            (row for row in current["documents"] if row["schema_name"] == schema and row["errors"]),
            key=lambda row: (-len(row["errors"]), row["doc_id"]),
        )
        if rows:
            row = rows[0]
            text = ocr_text(strict_json((dev / "inputs" / row["doc_id"] / "ocr.json").read_text()))
            feedback.append({"schema_name": schema, "ocr_text": text, "errors": row["errors"]})
    if not feedback:
        write_json(output / "reflection.json", {"skipped": "no development errors"})
        return None
    messages = [
        {"role": "system", "content": (
            "Improve OCR extraction instructions using development errors. Output only a short "
            "general instruction addendum, at most 200 words. Do not repeat the current prompt, "
            "include examples, or copy specific names, dates, identifiers or amounts from feedback. "
            "Keep all field values strings or null; never invent missing fields. "
            "Use previous candidate scores to avoid repeating an unsuccessful instruction."
        )},
        {"role": "user", "content": json.dumps({
            "current_prompt": current_prompt, "development_errors": feedback,
            "previous_candidates": history,
        }, ensure_ascii=False)},
    ]
    write_json(output / "request.json", {"messages": messages, "max_tokens": REFLECTION_TOKENS,
                                       "temperature": 0, "seed": 17})
    trace_id = f"reflection:round-{round_number}"
    mark = stack.mark()
    stack.set_trace_id(trace_id)
    report = {}
    try:
        report = chat(stack.direct_endpoint, stack.model, messages,
                      max_tokens=REFLECTION_TOKENS, timeout=330)
        report.update(observation(stack, mark, trace_id))
        content = report["content"].strip()
        reason = None
        if report["finish_reason"] != "stop":
            reason = "incomplete reflection"
        elif not content or len(content.split()) > 200 or len(content) > 4000:
            reason = "invalid reflection length"
        elif content == current_prompt.strip() or content == DIRECT_PROMPT.strip():
            reason = "unchanged prompt"
        report["rejection"] = reason
        if reason is None:
            candidate = DIRECT_PROMPT + "\n\n" + content
            (output / "candidate.txt").write_text(candidate + "\n")
            return candidate
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {"error_type": type(exc).__name__, **observation(stack, mark, trace_id)}
    finally:
        stack.set_trace_id(None)
        write_json(output / "reflection.json", report)
    return None


def metric_digest(metrics: dict) -> dict:
    return {key: value for key, value in metrics.items()
            if key not in {"documents", "by_template", "paired_ocr"}}


def run_experiment(args: argparse.Namespace, stack: ComparisonStack) -> None:
    root = args.output
    code = source_hashes()
    frozen = {
        "version": 1, "frozen_at_utc": now(), "synthetic_documents_only": True,
        "dataset": dataset_protocol(), "sources_sha256": code,
        "methods": list(METHODS), "model": stack.model, "max_tokens": MAX_TOKENS,
        "reflection_rounds": args.reflection_rounds, "reflection_max_tokens": REFLECTION_TOKENS,
        "selection_rule": "strictly greater development official score; retain incumbent on ties",
        "optimization_target": "direct model only, selected before observing holdout",
        "feedback_budget": "one highest-error development document per schema per round",
        "candidate_history": "include previous candidate prompts and development scores; skip duplicates",
        "holdout_generated": False, "weight_training": False,
        "method_order": list(METHODS), "document_order": "manifest order; serial requests",
        "request_templates": {
            method: {schema: build_request(
                method, schema, "OCR INPUT PLACEHOLDER", model=endpoint(stack, method)[1],
            ) for schema in SCHEMA_NAMES}
            for method in ["direct", "swarm", "ner"]
        },
        "model_call_upper_bound": 165 + 10 * args.reflection_rounds + (24 if args.reflection_rounds else 0),
        "budget_note": "Canary calls are separate; unchanged selected prompts reuse direct holdout results.",
    }
    write_json(root / "protocol.json", frozen)
    dev = root / "dev"
    generate_split(dev, "dev")
    dev_metrics = {
        method: run_method(stack, dev, root / f"dev-{method}", method, DIRECT_PROMPT)
        for method in METHODS
    }
    selected_name, selected_prompt = "direct", DIRECT_PROMPT
    selected_metrics = dev_metrics["direct"]
    decisions = []
    history = []
    seen_prompts = {DIRECT_PROMPT.strip()}
    for number in range(1, args.reflection_rounds + 1):
        directory = root / f"reflection-{number}"
        candidate = reflect(stack, dev, selected_metrics, selected_prompt, directory, number, history)
        decision = {"round": number, "incumbent": selected_name, "accepted": False}
        if candidate is not None and candidate.strip() not in seen_prompts:
            seen_prompts.add(candidate.strip())
            name = f"candidate-{number}"
            metrics = run_method(stack, dev, root / f"dev-{name}", "direct", candidate)
            dev_metrics[name] = metrics
            decision.update(candidate=name, score=metrics["official_score"]["score"],
                            incumbent_score=selected_metrics["official_score"]["score"])
            history.append({"prompt": candidate, "development_score": metrics["official_score"]["score"]})
            if metrics["official_score"]["score"] > selected_metrics["official_score"]["score"]:
                selected_name, selected_prompt, selected_metrics = name, candidate, metrics
                decision["accepted"] = True
        else:
            decision["skipped"] = "duplicate candidate" if candidate is not None else "no candidate"
        decisions.append(decision)
        write_json(directory / "decision.json", decision)
    if source_hashes() != code:
        raise RuntimeError("Experiment source changed after protocol freeze")
    (root / "selected-prompt.txt").write_text(selected_prompt + "\n")
    write_json(root / "selection.json", {
        "frozen_at_utc": now(), "selected": selected_name,
        "prompt_sha256": digest(root / "selected-prompt.txt"),
        "development_score": selected_metrics["official_score"]["score"],
        "decisions": decisions, "holdout_generated": False, "holdout_outputs_inspected": False,
    })
    # This is the only production holdout generation call, after selection is on disk.
    holdout = root / "holdout"
    generate_split(holdout, "holdout")
    holdout_metrics = {
        method: run_method(stack, holdout, root / f"holdout-{method}", method, DIRECT_PROMPT)
        for method in METHODS
    }
    if selected_name != "direct":
        holdout_metrics["selected"] = run_method(
            stack, holdout, root / "holdout-selected", "direct", selected_prompt,
        )
    else:
        holdout_metrics["selected"] = holdout_metrics["direct"]
    if source_hashes() != code:
        raise RuntimeError("Experiment source changed during evaluation")
    write_json(root / "results.json", {
        "completed_at_utc": now(), "selected_prompt": selected_name,
        "selected_reuses_direct": selected_name == "direct",
        "dev": {name: metric_digest(value) for name, value in dev_metrics.items()},
        "holdout": {name: metric_digest(value) for name, value in holdout_metrics.items()},
        "selection": decisions, "weight_training": False, "gepa_reproduction": False,
    })


def save_manifest(root: Path) -> None:
    excluded = {".log", ".db", ".sqlite", ".sqlite3"}
    files = {
        str(path.relative_to(root)): digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "sha256.json"
        and path.suffix not in excluded and "runtime" not in path.relative_to(root).parts
        and not path.name.endswith((".db-wal", ".db-shm"))
    }
    write_json(root / "sha256.json", files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--model-file", type=Path, required=True)
    parser.add_argument("--ner-repo", type=Path, required=True)
    parser.add_argument("--swarm-repo", type=Path, required=True)
    parser.add_argument("--reflection-rounds", type=int, choices=[0, 1, 2], default=2)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    complete = False
    try:
        with ComparisonStack(
            args.output / "stack", runner=args.runner, model_file=args.model_file,
            ner_repo=args.ner_repo, swarm_repo=args.swarm_repo,
        ) as stack:
            if args.preflight_only:
                complete = preflight(stack, args.output)
            else:
                run_experiment(args, stack)
                complete = True
    except BaseException as exc:
        write_json(args.output / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        save_manifest(args.output)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

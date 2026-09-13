"""Independently audit a completed comparison; never imports experiment code.

Usage: python verify_comparison_proxy.py RUN --output /outside/run/proxy-audit.json
Requires final results, frozen selection and closed service lifecycle.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path

TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def decode(raw: bytes):
    def invalid(value):
        raise ValueError("Non-finite constant: " + value)
    value = json.loads(raw.decode("utf-8"), parse_constant=invalid)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Non-finite JSON number")
    return value


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def usage(value):
    if not isinstance(value, dict):
        return None
    if not all(type(value.get(key)) is int and value[key] >= 0 for key in TOKEN_KEYS):
        return None
    return {key: value[key] for key in TOKEN_KEYS}


def compact(value):
    rendered = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    if len(rendered) <= 512:
        return value
    return {"type": type(value).__name__, "json_sha256": sha(rendered.encode()),
            "json_characters": len(rendered)}


class Audit:
    def __init__(self, root: Path):
        self.root = root
        self.mismatches = []
        self.notes = []
        self.calls = {}
        self.raw_request = {}
        self.raw_response = {}
        self.claims = defaultdict(list)
        self.observations = []
        self.run_reports = {}

    def issue(self, location, message, actual=None, expected=None):
        self.mismatches.append({"location": location, "message": message,
                                "actual": compact(actual), "expected": compact(expected)})

    def equal(self, location, field, actual, expected):
        if actual != expected or (isinstance(expected, bool) and type(actual) is not bool):
            self.issue(location, field + " differs", actual, expected)

    def load(self, path: Path):
        try:
            return decode(path.read_bytes())
        except (OSError, ValueError, RecursionError) as exc:
            self.issue(str(path.relative_to(self.root)), "Cannot load JSON: " + type(exc).__name__)
            return {}

    def body(self, directory: Path, record: dict, kind: str, location: str):
        name = record.get(kind + "_body_file")
        if not isinstance(name, str) or Path(name).name != name:
            self.issue(location, "Invalid body filename", name)
            return None, None
        path = directory / name
        try:
            raw = path.read_bytes()
        except OSError as exc:
            self.issue(location, "Cannot read raw body: " + type(exc).__name__, name)
            return name, None
        self.equal(location, kind + "_sha256", record.get(kind + "_sha256"), sha(raw))
        try:
            parsed = decode(raw) if raw else None
        except (ValueError, RecursionError):
            parsed = None
            if not record.get("error"):
                self.issue(location, "Unparseable raw body without proxy error", name)
        self.equal(location, "parsed " + kind, record.get(kind), parsed)
        return name, parsed

    def read_calls(self):
        directory = self.root / "stack" / "upstream"
        expected_body_files = set()
        for path in sorted(directory.glob("[0-9]*.json")):
            location = str(path.relative_to(self.root))
            record = self.load(path)
            if not isinstance(record, dict):
                self.issue(location, "Call metadata is not an object")
                continue
            call_id = record.get("call_id")
            if type(call_id) is not int or call_id < 1:
                self.issue(location, "Invalid call ID", call_id)
                continue
            self.equal(location, "filename", path.name, f"{call_id:06d}.json")
            if call_id in self.calls:
                self.issue(location, "Duplicate call ID", call_id)
                continue
            self.calls[call_id] = record
            for kind, target in (("request", self.raw_request), ("response", self.raw_response)):
                name, parsed = self.body(directory, record, kind, location)
                target[call_id] = parsed
                if name in expected_body_files:
                    self.issue(location, "Body file reused by another record", name)
                if name:
                    expected_body_files.add(name)
            raw_usage = self.call_usage(call_id)
            if raw_usage:
                self.equal(location, "token arithmetic", raw_usage["total_tokens"],
                           raw_usage["prompt_tokens"] + raw_usage["completion_tokens"])
            elapsed = record.get("elapsed_s")
            if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or elapsed < 0:
                self.issue(location, "Invalid proxy elapsed time", elapsed)
            else:
                self.equal(location, "latency_ms", record.get("latency_ms"), round(elapsed * 1000, 3))
            if record.get("error") is None:
                self.equal(location, "successful proxy status", record.get("status"), record.get("upstream_status"))
        ids = sorted(self.calls)
        self.equal("stack/upstream", "sequential call IDs", ids, list(range(1, len(ids) + 1)))
        found_bodies = {path.name for path in directory.glob("*.body")}
        self.equal("stack/upstream", "referenced raw-body files", sorted(found_bodies), sorted(expected_body_files))

    def call_usage(self, call_id):
        response = self.raw_response.get(call_id)
        return usage(response.get("usage")) if isinstance(response, dict) else None

    def inference_ids(self):
        return [key for key, row in self.calls.items()
                if row.get("method") == "POST" and row.get("path", "").endswith("/chat/completions")]

    def upstream_failed(self, call_id):
        row = self.calls[call_id]
        return row.get("upstream_status") != 200 or bool(row.get("error"))

    def truncated(self, call_id):
        response = self.raw_response.get(call_id)
        return isinstance(response, dict) and any(
            isinstance(choice, dict) and choice.get("finish_reason") == "length"
            for choice in response.get("choices", []))

    def check_observation(self, location, row, trace_id, split, method, run, category):
        if "trace_id" in row:
            self.equal(location, "trace_id", row["trace_id"], trace_id)
        expected_ids = [key for key in self.inference_ids() if self.calls[key].get("trace_id") == trace_id]
        stated_ids = row.get("upstream_call_ids")
        self.equal(location, "upstream_call_ids", stated_ids, expected_ids)
        self.equal(location, "observed_calls", row.get("observed_calls"), len(expected_ids))
        if isinstance(stated_ids, list):
            for call_id in stated_ids:
                if type(call_id) is int:
                    self.claims[call_id].append(location)
                else:
                    self.issue(location, "Non-integer claimed call ID", call_id)
        channel = "direct" if method in {"direct", "reflection"} else method
        for call_id in expected_ids:
            self.equal(location, f"call {call_id} channel", self.calls[call_id].get("channel"), channel)
        values = [self.call_usage(call_id) for call_id in expected_ids]
        complete = all(value is not None for value in values)
        tokens = {key: sum(value[key] for value in values) if complete else None for key in TOKEN_KEYS}
        self.equal(location, "observed_usage_complete", row.get("observed_usage_complete"), complete)
        self.equal(location, "observed_usage", row.get("observed_usage"), tokens)
        errors = [key for key in expected_ids if self.upstream_failed(key)]
        truncations = sum(self.truncated(key) for key in expected_ids)
        self.equal(location, "upstream_errors", row.get("upstream_errors"), errors)
        self.equal(location, "observed_truncated_responses", row.get("observed_truncated_responses"), truncations)
        if row.get("calls") is not None:
            self.equal(location, "service-reported calls", row["calls"], len(expected_ids))
        reported_usage = usage(row.get("usage"))
        if reported_usage is not None and complete:
            self.equal(location, "service-reported token usage", reported_usage, tokens)
        response = row.get("raw_response")
        if method == "direct" and len(expected_ids) == 1:
            self.equal(location, "direct request identity", row.get("request_body"), self.raw_request[expected_ids[0]])
            if not self.calls[expected_ids[0]].get("error"):
                self.equal(location, "direct response identity", response, self.raw_response[expected_ids[0]])
        if method == "ner" and isinstance(response, dict) and isinstance(response.get("meta"), dict):
            meta = response["meta"]
            self.equal(location, "NER attempts", meta.get("attempts"), len(expected_ids))
            self.equal(location, "NER cache hit", meta.get("cache_hit"), False)
            if complete and isinstance(response.get("data"), dict):
                self.equal(location, "NER raw service usage", usage(response["data"].get("usage")), tokens)
        if method == "swarm" and isinstance(response, dict) and isinstance(response.get("swarm"), dict):
            calls = response["swarm"].get("calls", [])
            self.equal(location, "Swarm raw call count", len(calls), len(expected_ids))
            for number, (service_call, call_id) in enumerate(zip(calls, expected_ids)):
                self.equal(location, f"Swarm call {number} usage", usage(service_call.get("usage")), self.call_usage(call_id))
                request = self.raw_request.get(call_id)
                if isinstance(request, dict):
                    self.equal(location, f"Swarm call {number} model", service_call.get("model"), request.get("model"))
            if complete:
                self.equal(location, "Swarm raw aggregate usage", usage(response.get("usage")), tokens)
        if method == "reflection" and len(expected_ids) == 1:
            raw = self.raw_response[expected_ids[0]]
            if isinstance(raw, dict) and raw.get("choices") and "content" in row:
                self.equal(location, "reflection content", row["content"], raw["choices"][0].get("message", {}).get("content"))
                self.equal(location, "reflection finish reason", row.get("finish_reason"), raw["choices"][0].get("finish_reason"))
        record_status = row.get("record", {}).get("status")
        item = {
            "location": location, "trace_id": trace_id, "split": split, "method": method,
            "run": run, "category": category, "call_ids": expected_ids,
            "document_status": record_status, "service_error": row.get("error") or row.get("error_type"),
            "reported_calls": row.get("calls"), "reported_usage": reported_usage,
            "finish_reason": row.get("finish_reason"), "elapsed_seconds": row.get("elapsed_seconds"),
            "upstream_errors": errors, "upstream_truncations": truncations,
        }
        self.observations.append(item)
        return item

    def read_observations(self):
        for path in sorted(self.root.glob("*/traces.jsonl")):
            run = path.parent.name
            split = run.split("-", 1)[0]
            settings = self.load(path.parent / "settings.json")
            method = settings.get("method")
            category = "candidate" if "-candidate-" in run else "selected" if run == "holdout-selected" else "baseline"
            rows = []
            document_ids = []
            for line_number, raw in enumerate(path.read_bytes().splitlines(), 1):
                location = f"{run}/traces.jsonl:{line_number}"
                try:
                    row = decode(raw)
                except ValueError:
                    self.issue(location, "Malformed JSONL record")
                    continue
                self.equal(location, "method", row.get("method"), method)
                document_ids.append(row.get("doc_id"))
                item = self.check_observation(location, row, f"{run}:{row.get('doc_id')}",
                                              split, method, run, category)
                rows.append(item)
            manifest = self.load(self.root / split / "manifest.json")
            self.equal(run, "manifest document order", document_ids,
                       [item["doc_id"] for item in manifest.get("documents", [])])
            aggregate = self.aggregate(rows)
            self.run_reports[run] = aggregate
            metrics = self.load(path.parent / "metrics.json")
            self.equal(run, "metrics document count", metrics.get("num_docs"), len(rows))
            self.equal(run, "metrics observed calls", metrics.get("calls", {}).get("observed"), aggregate["upstream_calls"])
            self.equal(run, "metrics known observed calls", metrics.get("calls", {}).get("known_observed"), aggregate["upstream_calls"])
            self.equal(run, "metrics observed usage completeness", metrics.get("observed_usage_complete"), aggregate["usage_complete"])
            self.equal(run, "metrics observed tokens", metrics.get("observed_tokens"), aggregate["tokens"])
            self.equal(run, "metrics invalid predictions", metrics.get("invalid_predictions"), aggregate["failed_documents"])
            self.equal(run, "metrics observed truncations", metrics.get("observed_truncated_responses"), aggregate["truncated_upstream_calls"])
            self.equal(run, "metrics final truncations", metrics.get("truncated_responses"), aggregate["truncated_final_responses"])
        for path in sorted(self.root.glob("reflection-*/reflection.json")):
            row = self.load(path)
            run = path.parent.name
            if row.get("skipped"):
                self.notes.append({"location": str(path.relative_to(self.root)), "reflection_skipped": row["skipped"]})
                continue
            number = run.rsplit("-", 1)[-1]
            self.check_observation(str(path.relative_to(self.root)), row,
                                   f"reflection:round-{number}", "dev", "reflection", run, "reflection")
        preflight = self.root / "preflight.json"
        if preflight.exists():
            for method, row in self.load(preflight).get("methods", {}).items():
                self.check_observation(f"preflight.json:{method}", row, f"preflight:{method}",
                                       "preflight", method, "preflight", "preflight")

    def check_final_result_totals(self):
        final = self.load(self.root / "results.json")
        expected_runs = set()
        for split in ("dev", "holdout"):
            for method, metrics in final.get(split, {}).items():
                reused = split == "holdout" and method == "selected" and final.get("selected_reuses_direct")
                run = f"{split}-direct" if reused else f"{split}-{method}"
                expected_runs.add(run)
                aggregate = self.run_reports.get(run)
                if aggregate is None:
                    self.issue("results.json", "Final results refer to a missing run", run)
                    continue
                location = f"results.json:{split}/{method}"
                self.equal(location, "observed calls", metrics.get("calls", {}).get("observed"),
                           aggregate["upstream_calls"])
                self.equal(location, "observed tokens", metrics.get("observed_tokens"), aggregate["tokens"])
                self.equal(location, "invalid predictions", metrics.get("invalid_predictions"),
                           aggregate["failed_documents"])
                self.equal(location, "observed truncations", metrics.get("observed_truncated_responses"),
                           aggregate["truncated_upstream_calls"])
        self.equal("results.json", "complete run inventory", sorted(self.run_reports), sorted(expected_runs))
        if not expected_runs:
            self.issue("results.json", "No final experiment runs were found")

    def aggregate(self, rows):
        ids = sorted({call_id for row in rows for call_id in row["call_ids"]})
        return {"observations": len(rows), "document_predictions": sum(row["document_status"] is not None for row in rows),
                "failed_documents": sum(row["document_status"] not in {None, "ok"} for row in rows),
                "document_statuses": dict(Counter(row["document_status"] for row in rows if row["document_status"] is not None)),
                "service_errors": dict(Counter(row["service_error"] for row in rows if row["service_error"])),
                "unknown_reported_calls": sum(row["reported_calls"] is None for row in rows if row["method"] != "reflection"),
                "truncated_final_responses": sum(row["finish_reason"] == "length" for row in rows),
                "adapter_seconds": round(sum(row["elapsed_seconds"] or 0 for row in rows), 6),
                **self.aggregate_calls(ids)}

    def aggregate_calls(self, ids):
        values = [self.call_usage(key) for key in ids]
        complete = all(value is not None for value in values)
        known = {key: sum(value[key] for value in values if value is not None) for key in TOKEN_KEYS}
        return {"upstream_calls": len(ids), "call_ids": ids, "usage_complete": complete,
                "tokens": known if complete else {key: None for key in TOKEN_KEYS},
                "known_tokens": known, "calls_without_usage": [key for key in ids if self.call_usage(key) is None],
                "failed_upstream_calls": sum(self.upstream_failed(key) for key in ids),
                "truncated_upstream_calls": sum(self.truncated(key) for key in ids),
                "upstream_seconds": round(sum(self.calls[key].get("elapsed_s", 0) for key in ids), 6)}

    def run(self):
        self.read_calls()
        self.read_observations()
        self.check_final_result_totals()
        inference = self.inference_ids()
        for key in inference:
            if not self.calls[key].get("trace_id"):
                self.issue(f"call {key}", "Unattributed upstream inference")
            if len(self.claims[key]) != 1:
                self.issue(f"call {key}", "Inference must be claimed exactly once", self.claims[key])
        for key in self.claims:
            if key not in inference:
                self.issue(f"call {key}", "Observation claims a nonexistent/non-inference call", self.claims[key])
        non_inference = [key for key in self.calls if key not in inference]
        if non_inference:
            self.issue("stack/upstream", "Non-inference calls require explicit separate accounting", non_inference)
        return {
            "verified_at_utc": datetime.now(UTC).isoformat(), "root": str(self.root),
            "verifier_sha256": sha(Path(__file__).read_bytes()), "passed": not self.mismatches,
            "scope": "raw proxy integrity and accounting; does not recalculate extraction quality",
            "raw_call_records": len(self.calls), "non_inference_call_ids": non_inference,
            "whole_run": self.aggregate(self.observations),
            "all_raw_inference": self.aggregate_calls(inference),
            "by_run": self.run_reports,
            "by_category": {category: self.aggregate([row for row in self.observations if row["category"] == category])
                            for category in sorted({row["category"] for row in self.observations})},
            "by_split_method": {f"{split}/{method}": self.aggregate([
                row for row in self.observations if row["split"] == split and row["method"] == method])
                for split, method in sorted({(row["split"], row["method"]) for row in self.observations})},
            "mismatch_count": len(self.mismatches), "mismatches": self.mismatches, "notes": self.notes,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.run.resolve(), args.output.resolve()
    if not (root / "results.json").is_file() or not (root / "selection.json").is_file():
        parser.error("Refusing evidence inspection before final results and frozen selection exist")
    lifecycle = decode((root / "stack/lifecycle.json").read_bytes())
    if lifecycle.get("status") != "closed":
        parser.error("Refusing evidence inspection while services remain active")
    if output.is_relative_to(root):
        parser.error("Write the audit outside the immutable experiment evidence directory")
    if output.exists():
        parser.error("Use a new output file; previous audits are never overwritten")
    report = Audit(root).run()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "passed": report["passed"],
                      "mismatches": report["mismatch_count"],
                      "inference_calls": report["all_raw_inference"]["upstream_calls"]}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

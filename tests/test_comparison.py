from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from rl_kyc_task_env import comparison as c
from rl_kyc_task_env.experiments import write_json
from rl_kyc_task_env.schemas import field_names


def prediction(schema="government_id", **values):
    return {"schema_name": schema, "fields": {name: values.get(name) for name in field_names(schema)}}


def chat_response(content=None, *, usage=None, finish="stop"):
    return {"model": "fixture", "choices": [{"message": {"role": "assistant", "content":
            json.dumps(prediction(full_name="Alice")) if content is None else content},
            "finish_reason": finish}], "usage": usage}


def ner_response(entities=None, **meta):
    return {"data": {"model": "fixture", "provider": "fixture", "entities": entities or [],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}},
            "meta": {"attempts": 1, "cache_hit": False, "warnings": [], **meta}}


@contextmanager
def endpoint(body, *, status=200, delay=0, headers=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append({"body": json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                             "headers": dict(self.headers), "path": self.path})
            time.sleep(delay)
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/extract", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class RequestContractsTest(unittest.TestCase):
    def test_same_source_text_and_schema_with_swarm_sampling_preserved(self):
        direct = c.build_request("direct", "government_id", "Alice", model="fixture")
        swarm = c.build_request("swarm", "government_id", "Alice", model="ensemble")
        ner = c.build_request("ner", "government_id", "Alice", model="fixture")
        self.assertEqual(direct["messages"], swarm["messages"])
        self.assertEqual(json.loads(direct["messages"][1]["content"])["ocr_text"], ner["text"])
        self.assertEqual(direct["response_format"], swarm["response_format"])
        self.assertTrue(direct["response_format"]["json_schema"]["strict"])
        self.assertEqual(direct["temperature"], 0)
        self.assertNotIn("temperature", swarm)
        self.assertEqual(ner["config"]["retries"], 1)
        self.assertTrue(ner["config"]["require_offsets"])
        self.assertEqual({r["name"] for r in ner["config"]["labels"]},
                         {name.upper() for name in field_names("government_id")})

    def test_roles_distinguish_customer_provider_and_payer_payee(self):
        for schema, pairs in [("proof_of_address", [("full_name", "issuer_name"), ("city", "postal_code")]),
                              ("payment_receipt", [("sender_name", "recipient_name")])]:
            body = c.build_request("ner", schema, "document", model="fixture")
            descriptions = {r["name"]: r["description"] for r in body["config"]["labels"]}
            for first, second in pairs:
                self.assertNotEqual(descriptions[first.upper()], descriptions[second.upper()])

    def test_invalid_config_fails_before_network(self):
        with patch.object(c, "build_opener", side_effect=AssertionError("network reached")):
            for kwargs in [{"timeout": 0}, {"timeout": True}, {"timeout": float("inf")},
                           {"max_tokens": True}, {"max_tokens": 0}, {"trace_id": "bad\nheader"},
                           {"endpoint": "https://user:password@example.com/extract"}]:
                args = {"endpoint": "http://127.0.0.1:1/v1/chat/completions", "model": "fixture", **kwargs}
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    c.infer_document("direct", "government_id", "Alice", **args)

    def test_geometry_text_preserves_source_without_loading_any_files(self):
        ocr = {"pages": [{"page_index": 0, "tokens": [
            {"text": "Aliçe", "bbox": [10, 20, 50, 30], "block_id": 2, "line_id": 1}]}]}
        with patch.object(Path, "read_text", side_effect=AssertionError("file read")):
            self.assertEqual(c.ocr_text(ocr), "[page=0 block=2 line=1 x=10 y=20] Aliçe")


class NerMappingTest(unittest.TestCase):
    def test_unicode_offsets_roles_missing_fields_and_exact_surfaces(self):
        text = "😀 José sent €20.00 to Café"
        entities = [{"text": "José", "label": "SENDER_NAME", "start": 2, "end": 6},
                    {"text": "Café", "label": "RECIPIENT_NAME", "start": 22, "end": 26}]
        got, conflicts = c.ner_prediction("payment_receipt", text, entities)
        self.assertEqual(got, prediction("payment_receipt", sender_name="José", recipient_name="Café"))
        self.assertEqual(conflicts, [])

    def test_conflicting_values_abstain_and_repeated_identical_values_agree(self):
        text = "Alice Bob Alice"
        entities = [{"text": "Alice", "label": "FULL_NAME", "start": 0, "end": 5},
                    {"text": "Alice", "label": "FULL_NAME", "start": 10, "end": 15}]
        got, conflicts = c.ner_prediction("government_id", text, entities)
        self.assertEqual(got["fields"]["full_name"], "Alice")
        self.assertEqual(conflicts, [])
        entities.append({"text": "Bob", "label": "FULL_NAME", "start": 6, "end": 9})
        got, conflicts = c.ner_prediction("government_id", text, entities)
        self.assertIsNone(got["fields"]["full_name"])
        self.assertEqual(conflicts, ["full_name"])

    def test_bad_offsets_unknown_labels_overlap_and_types_are_rejected(self):
        good = {"text": "Alice", "label": "FULL_NAME", "start": 0, "end": 5}
        variants = [{**good, "start": True}, {**good, "end": 6}, {**good, "start": -1},
                    {**good, "label": "PERSON"}, {**good, "text": "Bob"},
                    {**good, "confidence": 1}, {**good, "end": None}, {**good, "text": ""}]
        for bad in variants:
            with self.subTest(entity=bad), self.assertRaises(ValueError):
                c.ner_prediction("government_id", "Alice", [bad])
        with self.assertRaises(ValueError):
            c.ner_prediction("government_id", "Alice", [good, good])

    def test_missing_entities_fill_complete_null_schema(self):
        for schema in c.SCHEMA_NAMES:
            got, conflicts = c.ner_prediction(schema, "Empty document", [])
            self.assertEqual(got, prediction(schema))
            self.assertFalse(conflicts)


class ServiceContractsTest(unittest.TestCase):
    def run_direct(self, body, **options):
        with endpoint(body, **options) as (url, requests):
            result = c.infer_document("direct", "government_id", "Alice", endpoint=url,
                                      model="fixture", trace_id="doc:direct", api_key="fixture-secret")
        return result, requests

    def test_real_http_preserves_request_raw_response_tokens_and_trace_id(self):
        body = chat_response(usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})
        got, requests = self.run_direct(body)
        self.assertEqual(got["record"], {"status": "ok", "prediction": prediction(full_name="Alice")})
        self.assertEqual(got["raw_response"], body)
        self.assertEqual(got["request_body"], requests[0]["body"])
        self.assertEqual(got["calls"], 1)
        self.assertEqual(got["usage"]["total_tokens"], 12)
        self.assertEqual(requests[0]["headers"]["X-Kyc-Trace-Id"], "doc:direct")
        self.assertEqual(requests[0]["headers"]["Authorization"], "Bearer fixture-secret")
        self.assertNotIn("fixture-secret", json.dumps(got))

    def test_invalid_model_content_is_failure_not_repaired(self):
        for content, reason, error in [("```json\n{}\n```", "stop", "invalid_json"),
                                       (json.dumps(prediction()), "length", "truncated_response"),
                                       ("{}", "stop", "schema_mismatch")]:
            got, _ = self.run_direct(chat_response(content, finish=reason))
            self.assertEqual(got["record"], {"status": "invalid_prediction"})
            self.assertEqual(got["error"], error)
            self.assertEqual(got["calls"], 1)
            self.assertEqual(got["content"], content)

    def test_missing_usage_remains_unknown_and_invalid_usage_rejected(self):
        got, _ = self.run_direct(chat_response())
        self.assertIsNone(got["usage"])
        for usage in [{"prompt_tokens": True}, {"completion_tokens": -1},
                      {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 5}, []]:
            with self.subTest(usage=usage):
                got, _ = self.run_direct(chat_response(usage=usage))
                self.assertEqual(got["error"], "invalid_service_response")
                self.assertEqual(got["record"]["status"], "runtime_exception")

    def test_http_errors_preserve_bounded_redacted_response(self):
        for status in [401, 429, 500]:
            got, _ = self.run_direct({"error": "fixture-secret denied"}, status=status)
            self.assertEqual(got["http_status"], status)
            self.assertEqual(got["error"], "http_error")
            self.assertEqual(got["record"]["status"], "runtime_exception")
            self.assertEqual(got["raw_response"], {"error": "[redacted] denied"})
            self.assertIsNone(got["calls"])

    def test_oversized_invalid_utf8_duplicate_json_and_timeout_are_saved(self):
        for raw in [b"\xff", b'{"choices":[],"choices":[]}', b'{"invalid":"\\ud800"}',
                    b"[" * 2000 + b"0" + b"]" * 2000]:
            got, _ = self.run_direct(raw)
            self.assertEqual(got["error"], "invalid_service_response")
            self.assertIsNotNone(got["raw_response"])
        with patch.object(c, "MAX_RESPONSE_BYTES", 10):
            got, _ = self.run_direct(b"x" * 12)
        self.assertEqual(got["error"], "oversized_response")
        self.assertEqual(len(got["raw_response"]["prefix"]), 10)
        with endpoint(chat_response(), delay=.05) as (url, _):
            got = c.infer_document("direct", "government_id", "Alice", endpoint=url, model="fixture", timeout=.01)
        self.assertEqual(got["error"], "transport_error")

    def test_redirect_does_not_forward_credentials_or_create_second_request(self):
        with endpoint(chat_response()) as (destination, forwarded):
            got, _ = self.run_direct({}, status=307, headers={"Location": destination})
        self.assertFalse(forwarded)
        self.assertEqual(got["http_status"], 307)
        self.assertEqual(got["error"], "http_error")

    def test_actual_ner_envelope_and_protocol_violations(self):
        entity = {"text": "Alice", "label": "FULL_NAME", "start": 0, "end": 5}
        with endpoint(ner_response([entity])) as (url, requests):
            got = c.infer_document("ner", "government_id", "Alice", endpoint=url, model="fixture")
        self.assertEqual(got["record"], {"status": "ok", "prediction": prediction(full_name="Alice")})
        self.assertEqual(got["calls"], 1)
        self.assertEqual(requests[0]["body"]["config"]["retries"], 1)
        for meta in [{"attempts": 0, "cache_hit": True}, {"attempts": 2}, {"attempts": True}]:
            with endpoint(ner_response([entity], **meta)) as (url, _):
                got = c.infer_document("ner", "government_id", "Alice", endpoint=url, model="fixture")
            self.assertEqual(got["error"], "invalid_service_response")

    def test_actual_swarm_metadata_aggregates_all_three_calls(self):
        usage = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
        body = chat_response(usage={key: 3 * value for key, value in usage.items()})
        body["swarm"] = {"degraded": False, "usage_complete": True, "calls": [
            {"stage": stage, "provider": "local", "model": "fixture", "status": "completed", "usage": usage}
            for stage in ["generator:0", "generator:1", "merger"]]}
        with endpoint(body) as (url, requests):
            got = c.infer_document("swarm", "government_id", "Alice", endpoint=url, model="ensemble")
        self.assertEqual(got["calls"], 3)
        self.assertEqual(got["usage"]["total_tokens"], 36)
        self.assertEqual(got["swarm"], body["swarm"])
        self.assertNotIn("temperature", requests[0]["body"])
        body["usage"]["prompt_tokens"] += 1
        body["usage"]["total_tokens"] += 1
        with endpoint(body) as (url, _):
            got = c.infer_document("swarm", "government_id", "Alice", endpoint=url, model="ensemble")
        self.assertEqual(got["error"], "invalid_service_response")


class ComparisonMetricsTest(unittest.TestCase):
    def fixture(self, root, *, invalid=False, unknown=False):
        docs, records, traces = [], {}, []
        for index, profile in enumerate(["clean", "standard_noise"]):
            name = f"doc_{index}"
            gold = prediction(full_name="Alice")
            got = prediction(full_name=" ALICE ") if index == 0 else prediction(full_name="Bob", document_number="invented")
            record = {"status": "invalid_prediction"} if invalid else {"status": "ok", "prediction": got}
            write_json(root / "dataset" / "inputs" / name / "meta.json",
                       {"schema_name": "government_id", "doc_id": name})
            write_json(root / "dataset" / "gold" / f"{name}.json", gold)
            docs.append({"doc_id": name, "schema_name": "government_id", "base_id": "base_1",
                         "ocr_profile": profile, "template": "fixture"})
            records[name] = record
            traces.append({"doc_id": name, "record": record, "elapsed_seconds": 1 + index,
                           "usage": None if unknown else {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                           "calls": None if unknown else 1, "observed_calls": 1,
                           "observed_truncated_responses": index,
                           "observed_usage_complete": True,
                           "observed_usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})
        write_json(root / "dataset" / "manifest.json", {"documents": docs})
        write_json(root / "run" / "predictions.json", {"version": 1, "documents": records})
        (root / "run" / "traces.jsonl").write_text("".join(json.dumps(t) + "\n" for t in traces))
        return traces

    def test_official_normalization_null_hallucinations_and_paired_costs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            result = c.summarize_comparison(root / "dataset", root / "run")
        self.assertEqual(result["correct_fields"], 10)
        self.assertEqual(result["exact_docs"], 1)
        self.assertEqual(result["hallucinated_nulls"], 1)
        self.assertEqual(result["null_fields"], 10)
        self.assertEqual(result["independent_base_documents"], 1)
        self.assertEqual(result["paired_ocr"][0]["field_accuracy_delta"], round(-2 / 6, 6))
        self.assertEqual(result["tokens"]["total_tokens"], 24)
        self.assertEqual(result["observed_truncated_responses"], 1)
        self.assertEqual(result["calls"]["observed"], 2)
        self.assertEqual(result["latency_seconds"]["median"], 1.5)
        # The trusted scorer macro-averages across all three schema names.
        self.assertEqual(result["official_score"]["score"], .2667)

    def test_invalid_predictions_do_not_receive_free_null_credit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, invalid=True)
            result = c.summarize_comparison(root / "dataset", root / "run")
        self.assertEqual(result["correct_fields"], 0)
        self.assertEqual(result["correct_nulls"], 0)
        self.assertEqual(result["invalid_predictions"], 2)
        self.assertEqual(result["official_score"]["score"], 0)

    def test_unknown_usage_not_misreported_as_free_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, unknown=True)
            result = c.summarize_comparison(root / "dataset", root / "run")
        self.assertEqual(result["tokens"], {key: None for key in c.TOKEN_KEYS})
        self.assertFalse(result["usage_complete"])
        self.assertIsNone(result["calls"]["reported"])
        self.assertEqual(result["calls"]["observed"], 2)
        self.assertEqual(result["observed_tokens"]["total_tokens"], 24)
        self.assertTrue(result["observed_usage_complete"])

    def test_trace_mismatch_or_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            traces = self.fixture(root)
            for values in [[traces[0], traces[0]],
                           [{**traces[0], "record": {"status": "runtime_exception"}}, traces[1]]]:
                (root / "run" / "traces.jsonl").write_text("".join(json.dumps(t) + "\n" for t in values))
                with self.assertRaises(ValueError):
                    c.summarize_comparison(root / "dataset", root / "run")


if __name__ == "__main__":
    unittest.main()

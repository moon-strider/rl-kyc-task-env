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
from urllib.error import HTTPError

from rl_kyc_task_env import experiments
from rl_kyc_task_env.evaluation import evaluate_predictions
from rl_kyc_task_env.schemas import SCHEMA_NAMES, field_names


def prediction(schema: str = "government_id", **fields) -> dict:
    return {"schema_name": schema, "fields": {name: fields.get(name) for name in field_names(schema)}}


def document(root: Path, name: str = "doc_1", schema: str = "government_id") -> Path:
    directory = root / name
    experiments.write_json(directory / "meta.json", {"doc_id": name, "schema_name": schema})
    experiments.write_json(directory / "ocr.json", {"pages": [{
        "page_index": 0, "width": 100, "height": 100,
        "tokens": [{"text": "ALICE", "bbox": [1, 2, 20, 10], "line_id": 0, "block_id": 0}],
    }]})
    return directory


def response(content: str, *, finish_reason: str = "stop") -> bytes:
    return json.dumps({
        "model": "fixture-model", "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 13, "completion_tokens": 7, "total_tokens": 20},
    }).encode()


@contextmanager
def endpoint(*replies: tuple[int, bytes], delay: float = 0):
    """Use real HTTP framing so request/response tests cover the transport boundary."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(body)})
            status, data = replies[min(len(received) - 1, len(replies) - 1)]
            if delay:
                time.sleep(delay)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/chat/completions", received
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


class ExperimentPredictionTest(unittest.TestCase):
    def test_accepts_complete_strings_and_explicit_missing_fields(self):
        for schema in SCHEMA_NAMES:
            with self.subTest(schema=schema):
                value = prediction(schema)
                self.assertEqual(experiments.parse_prediction(json.dumps(value), schema),
                                 {"status": "ok", "prediction": value})

    def test_rejects_wrappers_duplicates_nonfinite_and_incomplete_json(self):
        valid = json.dumps(prediction())
        cases = [
            f"```json\n{valid}\n```", f"Here is your answer: {valid}", valid + valid, valid[:-1],
            '{"schema_name":"government_id","schema_name":"government_id","fields":{}}',
            valid.replace('"full_name": null', '"full_name": null, "full_name": "Alice"'),
            valid.replace('"full_name": null', '"full_name": NaN'),
            valid.replace('"full_name": null', '"full_name": Infinity'),
            valid.replace('"full_name": null', '"full_name": -Infinity'),
            valid.replace('"full_name": null', '"full_name": 1e999'),
            valid.replace('"full_name": null', '"full_name": -1e999'),
        ]
        for text in cases:
            with self.subTest(content=text[:100]):
                self.assertEqual(experiments.parse_prediction(text, "government_id"),
                                 {"status": "invalid_prediction", "error": "invalid_json"})

    def test_rejects_schema_mismatch_without_repairing_output(self):
        missing = prediction()
        del missing["fields"]["full_name"]
        extra = prediction()
        extra["fields"]["unrequested"] = "value"
        for value in [None, [], {}, missing, extra, prediction(full_name=123),
                      prediction("payment_receipt"), {**prediction(), "explanation": "answer"}]:
            with self.subTest(value=value):
                self.assertEqual(experiments.parse_prediction(json.dumps(value), "government_id"),
                                 {"status": "invalid_prediction", "error": "schema_mismatch"})

    def test_length_finish_rejects_even_syntactically_complete_prediction(self):
        self.assertEqual(experiments.parse_prediction(json.dumps(prediction()), "government_id", "length"),
                         {"status": "invalid_prediction", "error": "truncated_response"})

    def test_deeply_nested_output_is_rejected_without_crashing(self):
        record = experiments.parse_prediction("[" * 2000 + "0" + "]" * 2000, "government_id")
        self.assertEqual(record["status"], "invalid_prediction")


class ExperimentEndpointTest(unittest.TestCase):
    def test_actual_post_preserves_request_parameters_and_usage(self):
        messages = [{"role": "system", "content": "Extract"}, {"role": "user", "content": "Alice"}]
        with endpoint((200, response(json.dumps(prediction(full_name="Alice"))))) as (url, requests):
            result = experiments.chat(url, "requested-model", messages, max_tokens=64, timeout=2, api_key="fixture-secret")
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request["path"], "/v1/chat/completions")
        self.assertEqual(request["headers"]["Authorization"], "Bearer fixture-secret")
        self.assertEqual(request["headers"]["Content-Type"], "application/json")
        self.assertEqual(request["body"]["messages"], messages)
        self.assertIs(type(request["body"]["max_tokens"]), int)
        self.assertEqual(request["body"]["max_tokens"], 64)
        self.assertEqual(request["body"]["temperature"], 0)
        self.assertEqual(request["body"]["model"], "requested-model")
        self.assertFalse(request["body"]["stream"])
        self.assertEqual(result["model"], "fixture-model")
        self.assertEqual(result["usage"]["total_tokens"], 20)
        self.assertEqual(result["finish_reason"], "stop")
        self.assertGreaterEqual(result["elapsed_seconds"], 0)

    def test_http_failures_propagate_without_fabricated_predictions(self):
        for status in [401, 429, 500]:
            with self.subTest(status=status), endpoint((status, b'{"error":"provider failure"}')) as (url, _):
                with self.assertRaises(HTTPError) as raised:
                    experiments.chat(url, "fixture", [], timeout=2)
                self.assertEqual(raised.exception.code, status)

    def test_rejects_oversized_and_invalid_provider_response(self):
        bodies = [b"x" * (experiments.MAX_RESPONSE_BYTES + 1), b"not-json", b"\xff", b"{}",
                  b'{"choices":[]}', b'{"choices":[{"message":{"content":null}}]}',
                  b'{"choices":[{"message":{"content":[]}}]}',
                  b'{"choices":[],"choices":[]}']
        for body in bodies:
            with self.subTest(size=len(body), prefix=body[:40]), endpoint((200, body)) as (url, _):
                with self.assertRaises((ValueError, KeyError, IndexError, TypeError)):
                    experiments.chat(url, "fixture", [], timeout=2)

    def test_response_timeout_is_enforced(self):
        with endpoint((200, response("{}")), delay=0.1) as (url, _):
            with self.assertRaises((TimeoutError, OSError)):
                experiments.chat(url, "fixture", [], timeout=0.02)

    def test_absent_or_null_usage_is_normalized_for_saved_trace_and_scoring(self):
        for absent in [False, True]:
            body = json.loads(response(json.dumps(prediction())))
            if absent:
                del body["usage"]
            else:
                body["usage"] = None
            with self.subTest(absent=absent), endpoint((200, json.dumps(body).encode())) as (url, _):
                result = experiments.chat(url, "fixture", [], timeout=2)
            self.assertEqual(result["usage"], {})
            # Saving a successful provider answer must stay possible when usage
            # is unavailable; this is a valid OpenAI-compatible response shape.
            json.dumps(result, allow_nan=False)

    def test_malformed_token_counters_are_rejected_at_transport_boundary(self):
        invalid_usage = [[], "unknown", 0, False]
        for field in ["prompt_tokens", "completion_tokens", "total_tokens"]:
            invalid_usage.extend({field: value} for value in [-1, 1.5, True, "5", None])
        for usage in invalid_usage:
            body = json.loads(response(json.dumps(prediction())))
            body["usage"] = usage
            with self.subTest(usage=usage), endpoint((200, json.dumps(body).encode())) as (url, _):
                with self.assertRaises(ValueError):
                    experiments.chat(url, "fixture", [], timeout=2)

    def test_exponent_overflow_in_provider_metadata_is_rejected(self):
        body = response(json.dumps(prediction())).replace(b'"total_tokens": 20', b'"total_tokens": 1e999')
        with endpoint((200, body)) as (url, _):
            with self.assertRaises(ValueError):
                experiments.chat(url, "fixture", [], timeout=2)

    def test_invalid_endpoints_and_generation_limits_fail_before_network_access(self):
        urls = ["file:///tmp/predictions", "http://example.com/v1/chat/completions",
                "https://user:secret@example.com/v1/chat/completions",
                "https://example.com/v1/chat/completions?api_key=secret", "https://example.com/path#secret"]
        with patch.object(experiments, "urlopen", side_effect=AssertionError("Network must not be reached")):
            for url in urls:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    experiments.chat(url, "fixture", [])
            for tokens in [0, -1, True, 1.5]:
                with self.subTest(max_tokens=tokens), self.assertRaises(ValueError):
                    experiments.chat("http://127.0.0.1:1/v1/chat/completions", "fixture", [], max_tokens=tokens)
            for timeout in [0, -1, float("nan"), float("inf")]:
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    experiments.chat("http://127.0.0.1:1/v1/chat/completions", "fixture", [], timeout=timeout)


class ExperimentArtifactsTest(unittest.TestCase):
    def test_prompt_only_reads_ocr_and_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = document(Path(temporary))
            (directory / "target.json").write_text("SECRET_TARGET")
            (directory / "image.png").write_bytes(b"SECRET_IMAGE")
            (directory.parent / "gold.json").write_text("SECRET_GOLD")
            # Prime static schema caching before tracking data reads.
            field_names("government_id")
            read_text = Path.read_text
            read_bytes = Path.read_bytes
            accessed = []

            def tracked_text(path, *args, **kwargs):
                accessed.append(path)
                return read_text(path, *args, **kwargs)

            def tracked_bytes(path, *args, **kwargs):
                accessed.append(path)
                return read_bytes(path, *args, **kwargs)

            with patch.object(Path, "read_text", tracked_text), patch.object(Path, "read_bytes", tracked_bytes):
                messages = experiments.build_messages(directory, "Extract only")
            self.assertEqual(set(accessed), {directory / "meta.json", directory / "ocr.json"})
            self.assertEqual(messages[0], {"role": "system", "content": "Extract only"})
            user = json.loads(messages[1]["content"])
            self.assertEqual(user["schema_name"], "government_id")
            self.assertEqual(set(user["required_fields"]), set(field_names("government_id")))
            self.assertEqual(user["ocr_lines"][0]["text"], "ALICE")
            self.assertNotIn("SECRET", json.dumps(messages))

    def test_infer_freezes_predictions_and_traces_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document(root / "inputs")
            output = root / "run"
            value = prediction(full_name="Alice")
            with endpoint((200, response(json.dumps(value)))) as (url, requests):
                args = (root / "inputs", output, "llm", "Use OCR", url, "fixture", 64, 2, "fixture-secret")
                experiments.infer(*args)
                frozen = {p.name: p.read_bytes() for p in output.iterdir()}
                with self.assertRaises(FileExistsError):
                    experiments.infer(*args)
            self.assertEqual(len(requests), 1)
            self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, frozen)
            envelope = json.loads(frozen["predictions.json"])
            self.assertEqual(envelope, {"version": 1, "documents": {"doc_1": {"status": "ok", "prediction": value}}})
            trace = json.loads(frozen["traces.jsonl"])
            self.assertEqual(trace["record"], envelope["documents"]["doc_1"])
            self.assertEqual(trace["usage"]["total_tokens"], 20)
            self.assertEqual(trace["messages"], requests[0]["body"]["messages"])
            self.assertEqual(trace["ocr_sha256"], experiments.sha256(root / "inputs" / "doc_1" / "ocr.json"))
            self.assertNotIn(b"fixture-secret", b"".join(frozen.values()))

    def test_provider_failure_and_invalid_prediction_do_not_stop_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for number in range(3):
                document(root / "inputs", f"doc_{number}")
            with endpoint((429, b'{"error":"sensitive-provider-error"}'),
                          (200, response("```json\n{}\n```")),
                          (200, response(json.dumps(prediction())))) as (url, requests):
                experiments.infer(root / "inputs", root / "run", "llm", "Extract", url, "fixture", 64, 2, "fixture-secret")
            self.assertEqual(len(requests), 3)
            records = json.loads((root / "run" / "predictions.json").read_text())["documents"]
            self.assertEqual([records[f"doc_{n}"]["status"] for n in range(3)],
                             ["runtime_exception", "invalid_prediction", "ok"])
            traces_text = (root / "run" / "traces.jsonl").read_text()
            self.assertNotIn("fixture-secret", traces_text)
            self.assertNotIn("sensitive-provider-error", traces_text)
            self.assertEqual(len(traces_text.splitlines()), 3)

    def test_invalid_endpoint_is_not_persisted_as_run_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document(root / "inputs")
            with self.assertRaises(ValueError):
                experiments.infer(root / "inputs", root / "run", "llm", "Extract",
                                  "https://user:secret@example.com/path", "fixture", 64, 2, None)
            self.assertFalse((root / "run").exists())

    def test_summarize_gives_invalid_output_zero_even_when_gold_fields_are_null(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docs, records, traces = [], {}, []
            for index, schema in enumerate(SCHEMA_NAMES):
                name = f"doc_{index}"
                document(root / "dataset" / "inputs", name, schema)
                gold = prediction(schema)
                experiments.write_json(root / "dataset" / "gold" / f"{name}.json", gold)
                docs.append({"doc_id": name, "schema_name": schema, "ocr_profile": "clean"})
                record = ({"status": "invalid_prediction", "error": "invalid_json"} if index == 0 else
                          {"status": "ok", "prediction": gold})
                records[name] = ({"status": "invalid_prediction"} if index == 0 else record)
                traces.append({"doc_id": name, "record": record, "elapsed_seconds": 1,
                               "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
            experiments.write_json(root / "dataset" / "manifest.json", {"documents": docs})
            experiments.write_json(root / "run" / "predictions.json", {"version": 1, "documents": records})
            (root / "run" / "traces.jsonl").write_text("".join(json.dumps(t) + "\n" for t in traces))
            result = experiments.summarize(root / "dataset", root / "run")
            self.assertEqual(result["documents"][0]["correct_fields"], 0)
            self.assertFalse(result["documents"][0]["exact_doc"])
            self.assertEqual(len(result["documents"][0]["errors"]), len(field_names("government_id")))
            self.assertEqual(result["exact_docs"], 2)
            self.assertEqual(result["invalid_json"], 1)
            self.assertEqual(result["invalid_predictions"], 1)
            self.assertEqual(result["tokens"]["total_tokens"], 45)
            self.assertEqual(result["official_score"], evaluate_predictions(
                records, root / "dataset" / "inputs", root / "dataset" / "gold", include_error_summary=True))
            self.assertEqual(result["official_score"]["score"], 0.6667)

    def test_summarize_supports_schema_subset_and_uses_official_canonicalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document(root / "dataset" / "inputs")
            gold = prediction(full_name="Alice Smith", date_of_birth="1990-01-01", document_number="AB123")
            got = prediction(full_name=" ALICE  SMITH ", date_of_birth="1 Jan 1990", document_number="ab 123")
            experiments.write_json(root / "dataset" / "gold" / "doc_1.json", gold)
            experiments.write_json(root / "dataset" / "manifest.json", {"documents": [
                {"doc_id": "doc_1", "schema_name": "government_id", "ocr_profile": "standard_noise"}]})
            record = {"status": "ok", "prediction": got}
            experiments.write_json(root / "run" / "predictions.json", {"version": 1, "documents": {"doc_1": record}})
            (root / "run" / "traces.jsonl").write_text(json.dumps({"record": record}) + "\n")
            result = experiments.summarize(root / "dataset", root / "run")
            self.assertEqual(result["field_accuracy"], 1)
            self.assertEqual(result["exact_docs"], 1)
            self.assertEqual(result["by_schema"]["government_id"]["field_accuracy"], 1)
            self.assertEqual(result["by_schema"]["payment_receipt"]["num_docs"], 0)

    def test_summarize_rejects_missing_or_extra_document_predictions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            experiments.write_json(root / "dataset" / "manifest.json", {"documents": [{"doc_id": "expected"}]})
            for records in [{}, {"unexpected": {"status": "runtime_exception"}}]:
                experiments.write_json(root / "run" / "predictions.json", {"version": 1, "documents": records})
                with self.subTest(records=records), self.assertRaises(ValueError):
                    experiments.summarize(root / "dataset", root / "run")

    def test_generator_is_deterministic_and_holdout_uses_disjoint_templates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Rendering is deterministic but unnecessary for this fixture; retain real
            # seeded field sampling and OCR noise while returning a tiny rendered page.
            boxes = [{"text": "ALICE", "x1": 10, "y1": 20, "x2": 40, "y2": 30,
                      "block_id": 0, "is_label": False}]
            with patch("generator.render.render_document", return_value=(None, boxes)):
                experiments.generate(root / "dev_a", 2345, 2, "dev")
                experiments.generate(root / "dev_b", 2345, 2, "dev")
                experiments.generate(root / "holdout", 2346, 2, "holdout")
            dev_a = json.loads((root / "dev_a" / "manifest.json").read_text())
            dev_b = json.loads((root / "dev_b" / "manifest.json").read_text())
            holdout = json.loads((root / "holdout" / "manifest.json").read_text())
            self.assertEqual(dev_a, dev_b)
            for path in (root / "dev_a").rglob("*.json"):
                self.assertEqual(path.read_bytes(), (root / "dev_b" / path.relative_to(root / "dev_a")).read_bytes())
            dev_templates = {d["template"] for d in dev_a["documents"]}
            self.assertTrue(dev_templates.isdisjoint(d["template"] for d in holdout["documents"]))
            self.assertEqual({d["ocr_profile"] for d in holdout["documents"]}, {"clean", "standard_noise"})
            self.assertFalse(any((root / "holdout" / "inputs").rglob("target.json")))
            self.assertEqual(len(list((root / "holdout" / "gold").glob("*.json"))), 6)
            with self.assertRaises(FileExistsError):
                experiments.generate(root / "dev_a", 2345, 2, "dev")


if __name__ == "__main__":
    unittest.main()

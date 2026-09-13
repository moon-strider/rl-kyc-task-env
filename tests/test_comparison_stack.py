"""Check recording boundaries and failed-startup cleanup without model inference."""

import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.comparison_stack import ComparisonStack, RecordingProxy, unused_port


@contextmanager
def upstream():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        body = b'{"choices":[],"usage":{"total_tokens":5}}'
        delay = 0

        def log_message(self, *_args):
            pass

        def do_POST(self):
            requests.append((self.headers.get("Authorization"), self.path))
            self.rfile.read(int(self.headers["Content-Length"]))
            time.sleep(self.delay)
            self.send_response(200)
            self.send_header("Content-Length", str(len(self.body)))
            self.end_headers()
            try:
                self.wfile.write(self.body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, requests, Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def post(proxy, path, body):
    connection = http.client.HTTPConnection(
        "127.0.0.1", proxy.server.server_port, timeout=5
    )
    try:
        connection.request(
            "POST", path, body=body, headers={"Authorization": "secret-test-key"}
        )
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


class ComparisonStackTests(unittest.TestCase):
    def setUp(self):
        resources = ExitStack()
        self.addCleanup(resources.close)
        self.tmp_path = Path(resources.enter_context(tempfile.TemporaryDirectory()))
        self.upstream = resources.enter_context(upstream())

    def test_deadline_interrupts_upstream_and_records_timeout(self):
        port, _requests, handler = self.upstream
        handler.delay = 0.2
        proxy = RecordingProxy(self.tmp_path / "traces", port, timeout=0.05)
        proxy.start()
        try:
            started = time.monotonic()
            status, _ = post(proxy, "/direct/v1/chat/completions", b'{"messages":[]}')
            assert status == 504
            assert time.monotonic() - started < 1
            row = proxy.traces_since(0)[0]
            assert row["error"] and row["status"] == 504
            assert (proxy.root / row["request_body_file"]).exists()
        finally:
            proxy.close()

    def test_records_every_route_exactly_without_forwarding_credentials(self):
        tmp_path, upstream = self.tmp_path, self.upstream
        port, requests, _handler = upstream
        proxy = RecordingProxy(tmp_path / "traces", port)
        proxy.start()
        try:
            mark = proxy.mark()
            proxy.set_trace_id("doc-001")
            body = '{"model":"test","messages":[{"content":"Привет"}]}'.encode()
            for channel in ("direct", "ner", "swarm"):
                status, response = post(proxy, f"/{channel}/v1/chat/completions", body)
                assert status == 200
                assert json.loads(response)["usage"]["total_tokens"] == 5
            traces = proxy.traces_since(mark)
            assert [row["call_id"] for row in traces] == [1, 2, 3]
            assert [row["channel"] for row in traces] == ["direct", "ner", "swarm"]
            assert all(row["trace_id"] == "doc-001" for row in traces)
            assert all(
                (proxy.root / row["request_body_file"]).read_bytes() == body
                for row in traces
            )
            assert requests == [(None, "/v1/chat/completions")] * 3
            assert all(
                b"secret-test-key" not in path.read_bytes()
                for path in proxy.root.iterdir()
            )
        finally:
            proxy.close()

    def test_invalid_numbers_and_oversize_responses_fail_with_evidence(self):
        tmp_path, upstream = self.tmp_path, self.upstream
        port, requests, handler = upstream
        proxy = RecordingProxy(tmp_path / "traces", port)
        proxy.body_limit = 64
        proxy.start()
        try:
            status, _ = post(proxy, "/direct/v1/chat/completions", b'{"bad":1e999}')
            assert status == 502
            assert requests == []
            handler.body = b'{"padding":"' + b"x" * 128 + b'"}'
            status, _ = post(proxy, "/direct/v1/chat/completions", b'{"messages":[]}')
            assert status == 502
            traces = proxy.traces_since(0)
            assert traces[0]["upstream_status"] is None
            assert traces[1]["upstream_status"] == 200
            assert "Response exceeds" in traces[1]["error"]
            assert (
                len((proxy.root / traces[1]["response_body_file"]).read_bytes()) == 65
            )
        finally:
            proxy.close()

    def test_failed_service_start_reaps_an_already_started_service(self):
        tmp_path = self.tmp_path

        class FailedStack(ComparisonStack):
            def start(self):
                port = unused_port()
                self._launch(
                    "first",
                    [
                        sys.executable,
                        "-m",
                        "http.server",
                        str(port),
                        "--bind",
                        "127.0.0.1",
                    ],
                    dict(os.environ),
                    port,
                    "/",
                    5,
                )
                self.started = self._processes[0][1]
                self._launch(
                    "second",
                    [sys.executable, "-c", "raise SystemExit(17)"],
                    dict(os.environ),
                    unused_port(),
                    "/",
                    5,
                )

        stack = FailedStack(
            tmp_path / "evidence",
            runner=tmp_path,
            model_file=tmp_path,
            ner_repo=tmp_path,
            swarm_repo=tmp_path,
        )
        with self.assertRaisesRegex(RuntimeError, "second exited"), stack:
            self.fail("Startup should have failed")
        assert stack.started.poll() is not None
        assert (
            json.loads((stack.evidence_dir / "lifecycle.json").read_text())["status"]
            == "closed"
        )

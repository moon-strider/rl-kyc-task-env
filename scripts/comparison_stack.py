"""Local comparison services and a recording proxy; nothing starts at import time."""

from __future__ import annotations

import hashlib
import http.client
import json
import math
import os
import signal
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def strict_json(body: bytes) -> object:
    def invalid(value: str):
        raise ValueError(f"Non-finite JSON constant: {value}")

    value = json.loads(body.decode("utf-8"), parse_constant=invalid)
    queue = [(value, 0)]
    while queue:
        item, depth = queue.pop()
        if depth > 64:
            raise ValueError("JSON exceeds the depth limit")
        if isinstance(item, dict):
            for key in item:
                key.encode("utf-8")
            queue.extend((entry, depth + 1) for entry in item.values())
        elif isinstance(item, list):
            queue.extend((entry, depth + 1) for entry in item)
        elif isinstance(item, str):
            item.encode("utf-8")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Non-finite JSON number")
    return value


class RecordingProxy:
    """Record exact bounded JSON bodies, without copying authorization headers."""

    def __init__(self, root: Path, upstream_port: int, timeout: float = 300):
        self.root = root
        root.mkdir(parents=True)
        self.upstream_port = upstream_port
        self.timeout = timeout
        self.body_limit = 2_097_152
        self._lock = threading.Lock()
        self._next_id = 0
        self._trace_id: str | None = None
        self._records: dict[int, dict] = {}
        self._connections: set[http.client.HTTPConnection] = set()
        self._active = 0
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.handle_request()

            def do_POST(self):
                self.handle_request()

            def handle_request(self):
                started = time.monotonic()
                with proxy._lock:
                    proxy._next_id += 1
                    call_id = proxy._next_id
                    proxy._active += 1
                    trace_id = proxy._trace_id or self.headers.get("X-KYC-Trace-ID")
                record = {
                    "call_id": call_id,
                    "trace_id": trace_id,
                    "started_at_utc": datetime.now(UTC).isoformat(),
                    "method": self.command,
                    "path": self.path,
                    "channel": None,
                    "request": None,
                    "response": None,
                    "status": None,
                    "upstream_status": None,
                    "error": None,
                }
                request_body = b""
                response_body = b""
                chunks = []
                connection = None
                upstream_socket = None
                timer = None
                status = 502
                try:
                    parsed = urlsplit(self.path)
                    parts = parsed.path.split("/", 2)
                    if (
                        len(parts) != 3
                        or parts[1] not in {"direct", "ner", "swarm"}
                        or parsed.query
                        or parsed.fragment
                    ):
                        raise ValueError("Unexpected proxy route")
                    record["channel"] = parts[1]
                    upstream_path = "/" + parts[2]
                    allowed = {("POST", "/v1/chat/completions"), ("GET", "/v1/models")}
                    if (self.command, upstream_path) not in allowed:
                        raise ValueError("Unexpected upstream method or path")
                    if self.headers.get("Transfer-Encoding"):
                        raise ValueError("Chunked client requests are unsupported")
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= length <= proxy.body_limit:
                        raise ValueError("Request exceeds the body limit")
                    self.connection.settimeout(10)
                    request_body = self.rfile.read(length)
                    if len(request_body) != length:
                        raise ValueError("Incomplete request body")
                    if self.command == "POST":
                        request = strict_json(request_body)
                        if (
                            not isinstance(request, dict)
                            or request.get("stream", False) is not False
                        ):
                            raise ValueError(
                                "Expected a non-streaming JSON request object"
                            )
                        record["request"] = request
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", proxy.upstream_port, timeout=proxy.timeout
                    )
                    with proxy._lock:
                        proxy._connections.add(connection)
                    deadline = time.monotonic() + proxy.timeout

                    def interrupt_upstream():
                        sock = upstream_socket or connection.sock
                        if sock is not None:
                            try:
                                sock.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass

                    timer = threading.Timer(proxy.timeout, interrupt_upstream)
                    timer.daemon = True
                    timer.start()
                    connection.request(
                        self.command,
                        upstream_path,
                        body=request_body or None,
                        headers={"Content-Type": "application/json"},
                    )
                    upstream_socket = connection.sock
                    response = connection.getresponse()
                    record["upstream_status"] = response.status
                    size = 0
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError(
                                "Upstream exceeded its response deadline"
                            )
                        if connection.sock is not None:
                            connection.sock.settimeout(remaining)
                        chunk = response.read(min(65_536, proxy.body_limit + 1 - size))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > proxy.body_limit:
                            raise ValueError("Response exceeds the body limit")
                    response_body = b"".join(chunks)
                    record["response"] = strict_json(response_body)
                    status = response.status
                except (
                    OSError,
                    ValueError,
                    RecursionError,
                    http.client.HTTPException,
                ) as exc:
                    status = (
                        504
                        if isinstance(exc, TimeoutError)
                        or (timer is not None and time.monotonic() >= deadline)
                        else 502
                    )
                    record["error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    if timer is not None:
                        timer.cancel()
                    if chunks:
                        response_body = b"".join(chunks)
                    if connection is not None:
                        connection.close()
                        with proxy._lock:
                            proxy._connections.discard(connection)
                    record["status"] = status
                    record["elapsed_s"] = round(time.monotonic() - started, 6)
                    record["latency_ms"] = round(record["elapsed_s"] * 1000, 3)
                    prefix = f"{call_id:06d}"
                    request_path = proxy.root / f"{prefix}.request.body"
                    response_path = proxy.root / f"{prefix}.response.body"
                    request_path.write_bytes(request_body)
                    response_path.write_bytes(response_body)
                    record["request_body_file"] = request_path.name
                    record["response_body_file"] = response_path.name
                    record["request_sha256"] = hashlib.sha256(request_body).hexdigest()
                    record["response_sha256"] = hashlib.sha256(
                        response_body
                    ).hexdigest()
                    write_json(proxy.root / f"{prefix}.json", record)
                    with proxy._lock:
                        proxy._records[call_id] = record
                        proxy._active -= 1
                body = (
                    json.dumps({"error": {"message": record["error"]}}).encode()
                    if record["error"]
                    else response_body
                )
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def start(self) -> None:
        self.thread.start()

    def set_trace_id(self, trace_id: str | None) -> None:
        if trace_id is not None and (
            not isinstance(trace_id, str) or len(trace_id) > 256
        ):
            raise ValueError("Trace ID must be text of at most 256 characters")
        with self._lock:
            if self._active:
                raise RuntimeError(
                    "Cannot change trace attribution during an upstream request"
                )
            self._trace_id = trace_id

    def mark(self) -> int:
        with self._lock:
            if self._active:
                raise RuntimeError("An upstream request is still running")
            return self._next_id

    def traces_since(self, mark: int) -> list[dict]:
        with self._lock:
            if self._active:
                raise RuntimeError("An upstream request is still running")
            return [self._records[key] for key in sorted(self._records) if key > mark]

    def close(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
        self.server.server_close()
        with self._lock:
            connections = list(self._connections)
        for connection in connections:
            if connection.sock is not None:
                try:
                    connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ComparisonStack:
    """Own llama.cpp, NER and Swarm processes in the caller's network namespace."""

    def __init__(
        self,
        evidence_dir: Path,
        *,
        runner: Path,
        model_file: Path,
        ner_repo: Path,
        swarm_repo: Path,
        model: str = "qwen3-4b-instruct-2507",
        max_tokens: int = 512,
        request_timeout: float = 300,
    ):
        self.evidence_dir = Path(evidence_dir).resolve()
        self.runner = Path(runner).resolve()
        self.model_file = Path(model_file).resolve()
        self.ner_repo = Path(ner_repo).resolve()
        self.swarm_repo = Path(swarm_repo).resolve()
        self.model = model
        self.swarm_model = "kyc-ensemble"
        self.max_tokens = max_tokens
        self.request_timeout = request_timeout
        self.provenance: dict = {}
        self._processes: list[tuple[str, subprocess.Popen, object]] = []
        self.proxy: RecordingProxy | None = None

    def __enter__(self):
        self.evidence_dir.mkdir(parents=True)
        try:
            self.start()
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self, *_args):
        self.close()

    def mark(self) -> int:
        assert self.proxy is not None
        return self.proxy.mark()

    def traces_since(self, mark: int) -> list[dict]:
        assert self.proxy is not None
        return self.proxy.traces_since(mark)

    def set_trace_id(self, trace_id: str | None) -> None:
        assert self.proxy is not None
        self.proxy.set_trace_id(trace_id)

    def start(self) -> None:
        model_port, ner_port, swarm_port = unused_port(), unused_port(), unused_port()
        if len({model_port, ner_port, swarm_port}) != 3:
            raise RuntimeError(
                "Port allocation collision; retry in a fresh evidence directory"
            )
        self.proxy = RecordingProxy(
            self.evidence_dir / "upstream", model_port, self.request_timeout
        )
        self.direct_endpoint = self.proxy.base_url + "/direct/v1/chat/completions"
        self.ner_endpoint = f"http://127.0.0.1:{ner_port}/v1/extract"
        self.swarm_endpoint = f"http://127.0.0.1:{swarm_port}/v1/chat/completions"
        self.proxy.start()
        env = {
            k: v
            for k, v in os.environ.items()
            if k in {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR"}
        }
        env["PYTHONNOUSERSITE"] = "1"
        llama_command = [
            str(self.runner),
            "--model",
            str(self.model_file),
            "--alias",
            self.model,
            "--host",
            "127.0.0.1",
            "--port",
            str(model_port),
            "--ctx-size",
            "16384",
            "--threads",
            "6",
            "--threads-batch",
            "6",
            "--parallel",
            "1",
            "--n-gpu-layers",
            "0",
            "--seed",
            "17",
            "--jinja",
            "--reasoning",
            "off",
            "--no-webui",
        ]
        ner_env = {
            "NER_PROVIDER": "llama_cpp",
            "NER_MODEL": self.model,
            "LLAMA_CPP_BASE_URL": self.proxy.base_url + "/ner/v1",
            "ALLOWED_MODELS": json.dumps([self.model]),
            "REQUEST_TIMEOUT_S": str(self.request_timeout),
            "TRANSPORT_RETRIES": "0",
            "MAX_ATTEMPTS": "1",
            "MAX_TOKENS": str(self.max_tokens),
            "MAX_OUTPUT_TOKENS": str(self.max_tokens),
            "CACHE_ENABLED": "false",
            "PROVIDER_CONCURRENCY_LIMIT": "1",
            "BATCH_CONCURRENCY": "1",
            "CONFIG_DB_PATH": str(self.evidence_dir / "ner-configs.db"),
        }
        ner_command = [
            str(self.ner_repo / ".venv/bin/python"),
            "-m",
            "uvicorn",
            "ner_service.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(ner_port),
            "--log-level",
            "warning",
        ]
        generator = {
            "provider": "local",
            "model": self.model,
            "max_tokens": self.max_tokens,
        }
        swarm_config = {
            "providers": {"local": {"base_url": self.proxy.base_url + "/swarm/v1"}},
            "swarms": {
                self.swarm_model: {
                    "generators": [
                        dict(generator, temperature=0),
                        dict(generator, temperature=0.4),
                    ],
                    "merger": dict(generator, temperature=0),
                    "min_success": 2,
                    "merger_failure": "error",
                }
            },
            "default_swarm": self.swarm_model,
            "limits": {
                "requests": 1,
                "provider_calls": 1,
                "timeout_seconds": 600,
                "output_tokens": self.max_tokens,
                "request_bytes": 2_097_152,
                "response_bytes": 2_097_152,
            },
        }
        config_path = self.evidence_dir / "swarm-config.json"
        write_json(config_path, swarm_config)
        write_json(self.evidence_dir / "ner-config.json", ner_env)
        swarm_command = [
            str(self.swarm_repo / ".venv/bin/swarm-of-experts"),
            "--config",
            str(config_path),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(swarm_port),
        ]
        repo_versions = {}
        for name, repo in (("ner", self.ner_repo), ("swarm", self.swarm_repo)):
            repo_versions[name] = {
                "path": str(repo),
                "commit": subprocess.check_output(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=10
                ).strip(),
                "dirty": bool(
                    subprocess.check_output(
                        ["git", "-C", str(repo), "status", "--porcelain"],
                        text=True,
                        timeout=10,
                    )
                ),
            }
        self.provenance = {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "model_file": str(self.model_file),
            "model_sha256": digest(self.model_file),
            "runner": str(self.runner),
            "runner_sha256": digest(self.runner),
            "runner_version": subprocess.check_output(
                [str(self.runner), "--version"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=10,
                env=env,
            ).strip(),
            "repositories": repo_versions,
            "model": self.model,
            "commands": {
                "llama": llama_command,
                "ner": ner_command,
                "swarm": swarm_command,
            },
            "ner_config": ner_env,
            "swarm_config": swarm_config,
            "proxy": {
                "timeout_seconds": self.request_timeout,
                "body_limit": self.proxy.body_limit,
            },
            "endpoints": {
                "direct": self.direct_endpoint,
                "ner": self.ner_endpoint,
                "swarm": self.swarm_endpoint,
            },
            "working_directory": str(self.evidence_dir),
        }
        write_json(self.evidence_dir / "provenance.json", self.provenance)
        self._launch("llama", llama_command, env, model_port, "/health", 90)
        self._launch("ner", ner_command, {**env, **ner_env}, ner_port, "/v1/ready", 45)
        self._launch("swarm", swarm_command, env, swarm_port, "/health", 45)
        write_json(self.evidence_dir / "lifecycle.json", {"status": "ready"})

    def _launch(
        self,
        name: str,
        command: list[str],
        env: dict[str, str],
        port: int,
        health_path: str,
        timeout: float,
    ) -> None:
        log = (self.evidence_dir / f"{name}.log").open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=self.evidence_dir,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except BaseException:
            log.close()
            raise
        self._processes.append((name, process, log))
        deadline = time.monotonic() + timeout
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited during startup; see {name}.log")
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            try:
                connection.request("GET", health_path)
                response = connection.getresponse()
                if response.status == 200:
                    return
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{name} startup deadline exceeded; see {name}.log")
            time.sleep(0.2)

    def close(self) -> None:
        stopped = []
        for name, process, log in reversed(self._processes):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            # A service leader can exit before its children; clean its whole group.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            log.close()
            stopped.append(
                {"service": name, "pid": process.pid, "returncode": process.returncode}
            )
        self._processes.clear()
        if self.proxy is not None:
            self.proxy.close()
        if self.evidence_dir.exists():
            write_json(
                self.evidence_dir / "lifecycle.json",
                {"status": "closed", "services": stopped},
            )

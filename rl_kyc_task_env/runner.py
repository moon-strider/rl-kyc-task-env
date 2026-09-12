from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

TIMEOUT_SECONDS = 5
MAX_PREDICTION_BYTES = 64 * 1024

_WORKER_CODE = r'''
import contextlib
import importlib.util
import json
import os
import sys
from pathlib import Path


def emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, allow_nan=False))


def main():
    solution_dir = Path(sys.argv[1])
    document_dir = sys.argv[2]
    extract_path = solution_dir / "extract.py"
    if not extract_path.is_file():
        emit({"status": "missing_extract"})
        return
    # Logs are discarded, not retained in an unbounded StringIO buffer.
    with open(os.devnull, "w") as sink:
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                sys.path.insert(0, str(solution_dir))
                spec = importlib.util.spec_from_file_location("participant_extract", extract_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                prediction = module.predict(document_dir)
            json.dumps(prediction, ensure_ascii=False, allow_nan=False)
        except (ImportError, FileNotFoundError, AttributeError):
            emit({"status": "import_failure"})
            return
        except (TypeError, ValueError, RecursionError):
            emit({"status": "non_serializable"})
            return
        except BaseException:
            emit({"status": "runtime_exception"})
            return
    emit({"status": "ok", "prediction": prediction})

main()
'''


def run_bounded_process(
    args: list[str], timeout_seconds: float, max_output_bytes: int
) -> subprocess.CompletedProcess[str]:
    """Bound pipe output and kill the entire local process group on exit.

    This is resource handling, not a sandbox. Docker callers must additionally
    remove their named container: killing the Docker CLI does not stop it.
    """
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout_seconds
    returncode = None
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    returncode = 124
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffer = output[key.data]
                    remaining_bytes = max_output_bytes - sum(len(value) for value in output.values())
                    buffer.extend(chunk[:remaining_bytes])
                    if len(chunk) > remaining_bytes:
                        returncode = 125
                        break
                if returncode is not None:
                    break
            if returncode is None:
                try:
                    returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    returncode = 124
        finally:
            # Kill workers remaining in the original process group, including ones
            # that closed their pipes. Detached sessions require Docker removal.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            process.stdout.close()
            process.stderr.close()
    stdout = output["stdout"].decode("utf-8", errors="replace")
    stderr = output["stderr"].decode("utf-8", errors="replace")
    if returncode == 124:
        stderr = f"Process timeout after {timeout_seconds} seconds"
    elif returncode == 125:
        stderr = f"Process output exceeded {max_output_bytes} bytes"
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def run_prediction_subprocess(
    solution_dir: Path, document_dir: Path, timeout_seconds: float = TIMEOUT_SECONDS
) -> tuple[str, Any | None]:
    """Run trusted code locally, or untrusted code ONLY inside an isolated collector.

    A local subprocess can access the caller's files and credentials. This
    function is not an isolation boundary; use run_hidden_judge for submissions.
    """
    try:
        completed = run_bounded_process(
            [sys.executable, "-c", _WORKER_CODE, str(solution_dir), str(document_dir)],
            timeout_seconds,
            MAX_PREDICTION_BYTES,
        )
    except OSError:
        return "runtime_exception", None
    if completed.returncode == 124:
        return "timeout", None
    if completed.returncode == 125:
        return "output_limit", None
    if completed.returncode != 0:
        return "runtime_exception", None
    try:
        payload = json.loads(completed.stdout)
    except (ValueError, RecursionError):
        return "runtime_exception", None
    if not isinstance(payload, dict):
        return "runtime_exception", None
    status = payload.get("status")
    if not isinstance(status, str):
        return "runtime_exception", None
    if status == "ok":
        return "ok", payload.get("prediction")
    if status in {"missing_extract", "import_failure", "runtime_exception", "non_serializable"}:
        return status, None
    return "runtime_exception", None

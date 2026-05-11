from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

TIMEOUT_SECONDS = 5

_WORKER_CODE = r"""
import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path


def emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, allow_nan=False))


def main() -> int:
    solution_dir = Path(sys.argv[1])
    document_dir = sys.argv[2]
    extract_path = solution_dir / "extract.py"
    if not extract_path.exists():
        emit({"status": "missing_extract"})
        return 0

    capture = io.StringIO()
    try:
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            spec = importlib.util.spec_from_file_location("participant_extract", extract_path)
            if spec is None or spec.loader is None:
                emit({"status": "import_failure"})
                return 0
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            predict = getattr(module, "predict")
            prediction = predict(document_dir)
        json.dumps(prediction, ensure_ascii=False, allow_nan=False)
    except (ImportError, FileNotFoundError, AttributeError):
        emit({"status": "import_failure"})
        return 0
    except (TypeError, ValueError):
        emit({"status": "non_serializable"})
        return 0
    except Exception:
        emit({"status": "runtime_exception"})
        return 0

    emit({"status": "ok", "prediction": prediction})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def run_prediction_subprocess(
    solution_dir: Path,
    document_dir: Path,
    timeout_seconds: int = TIMEOUT_SECONDS,
) -> tuple[str, Any | None]:
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _WORKER_CODE, str(solution_dir), str(document_dir)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", None
    except OSError:
        return "runtime_exception", None

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return "runtime_exception", None

    status = payload.get("status")
    if completed.returncode != 0:
        return "runtime_exception", None
    if status == "ok":
        return "ok", payload.get("prediction")
    if status in {"missing_extract", "import_failure", "runtime_exception", "non_serializable"}:
        return status, None
    return "runtime_exception", None

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task.tools.canonicalize import canonicalize_prediction

SCHEMA_NAMES = ("government_id", "proof_of_address", "payment_receipt")
SCHEMA_DIR = REPO_ROOT / "task" / "schemas"
TIMEOUT_SECONDS = 5

_SCHEMA_VALIDATORS = {
    schema_name: Draft7Validator(
        json.loads((SCHEMA_DIR / f"{schema_name}.schema.json").read_text(encoding="utf-8"))
    )
    for schema_name in SCHEMA_NAMES
}

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


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def list_document_dirs(dataset_dir: Path) -> list[Path]:
    if not dataset_dir.exists():
        return []
    return sorted(path for path in dataset_dir.iterdir() if path.is_dir())


def resolve_gold_path(document_dir: Path, gold_dir: Path | None = None) -> Path:
    if gold_dir is None:
        target_path = document_dir / "target.json"
    else:
        target_path = gold_dir / f"{document_dir.name}.json"
    if target_path.exists():
        return target_path
    raise FileNotFoundError(f"Could not locate gold target for {document_dir}")


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


def validate_prediction(schema_name: str, prediction: Any) -> bool:
    validator = _SCHEMA_VALIDATORS[schema_name]
    return validator.is_valid(prediction)


def score_document(schema_name: str, prediction: dict[str, Any], gold: dict[str, Any]) -> float:
    canonical_prediction = canonicalize_prediction(prediction)
    canonical_gold = canonicalize_prediction(gold)
    gold_fields = canonical_gold["fields"]
    prediction_fields = canonical_prediction["fields"]
    field_names = list(gold_fields.keys())
    matches = [
        1.0 if prediction_fields.get(field_name) == gold_fields.get(field_name) else 0.0
        for field_name in field_names
    ]
    field_acc = sum(matches) / len(matches)
    exact_doc = 1.0 if all(match == 1.0 for match in matches) else 0.0
    return 0.9 * field_acc + 0.1 * exact_doc


def evaluate_document(
    solution_dir: Path,
    document_dir: Path,
    gold_dir: Path | None = None,
) -> dict[str, Any]:
    meta = load_json(document_dir / "meta.json")
    schema_name = meta["schema_name"]
    gold = load_json(resolve_gold_path(document_dir, gold_dir))
    status, prediction = run_prediction_subprocess(solution_dir, document_dir)
    if status != "ok":
        return {"schema_name": schema_name, "score": 0.0, "status": status}
    if not validate_prediction(schema_name, prediction):
        return {"schema_name": schema_name, "score": 0.0, "status": "invalid_schema"}
    return {"schema_name": schema_name, "score": score_document(schema_name, prediction, gold), "status": "ok"}


def _rounded(value: float) -> float:
    return round(value, 4)


def aggregate_scores(
    doc_results: list[dict[str, Any]],
    include_error_summary: bool = False,
) -> dict[str, Any]:
    by_schema_docs: dict[str, list[float]] = defaultdict(list)
    status_counts: Counter[str] = Counter()
    for result in doc_results:
        by_schema_docs[result["schema_name"]].append(result["score"])
        status_counts[result["status"]] += 1

    raw_by_schema = {}
    by_schema = {}
    for schema_name in SCHEMA_NAMES:
        schema_scores = by_schema_docs.get(schema_name, [])
        schema_score = sum(schema_scores) / len(schema_scores) if schema_scores else 0.0
        raw_by_schema[schema_name] = schema_score
        by_schema[schema_name] = _rounded(schema_score)

    final_score = sum(raw_by_schema[schema_name] for schema_name in SCHEMA_NAMES) / len(SCHEMA_NAMES)
    result = {
        "score": _rounded(final_score),
        "by_schema": by_schema,
        "num_docs": len(doc_results),
    }
    if include_error_summary:
        result["error_summary"] = {
            status: count
            for status, count in sorted(status_counts.items())
            if status != "ok" and count > 0
        }
    return result


def evaluate_solution(
    solution_dir: Path,
    dataset_dir: Path,
    gold_dir: Path | None = None,
    include_error_summary: bool = False,
) -> dict[str, Any]:
    doc_results = [
        evaluate_document(solution_dir, document_dir, gold_dir)
        for document_dir in list_document_dirs(dataset_dir)
    ]
    return aggregate_scores(doc_results, include_error_summary=include_error_summary)


__all__ = [
    "REPO_ROOT",
    "SCHEMA_NAMES",
    "TIMEOUT_SECONDS",
    "aggregate_scores",
    "evaluate_document",
    "evaluate_solution",
    "list_document_dirs",
    "load_json",
    "resolve_gold_path",
    "run_prediction_subprocess",
    "score_document",
    "validate_prediction",
]

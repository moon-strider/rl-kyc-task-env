"""Build and test distribution artifacts in a clean venv outside the checkout.

Package installation may access the Python package registry. The runtime checks
need no provider credentials, Docker, external dataset, or running model.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CLI_NAMES = (
    "rl-kyc-public-validator",
    "rl-kyc-hidden-judge",
    "rl-kyc-harness",
    "rl-kyc-experiment",
)


def run(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {args!r}\n{result.stdout}\n{result.stderr}"
        )
    return result


def check_artifacts(dist: Path) -> Path:
    wheel, = dist.glob("*.whl")
    sdist, = dist.glob("*.tar.gz")
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        required = {
            "rl_kyc_task_env/__init__.py",
            "harness/cli/external_agent_eval.py",
            "task/tools/public_validator.py",
            "judge/run_judge.py",
            "generator/utils.py",
            "baselines/null_baseline/extract.py",
            "task/prompt.txt",
            *(f"task/schemas/{name}.schema.json" for name in (
                "government_id", "proof_of_address", "payment_receipt"
            )),
        }
        missing = required - names
        if missing:
            raise AssertionError(f"Wheel is missing runtime files: {sorted(missing)}")
        if sum(item.file_size for item in archive.infolist()) > 2_000_000:
            raise AssertionError("Wheel unexpectedly exceeds 2 MB uncompressed")
    with tarfile.open(sdist) as archive:
        names.update(str(Path(name).relative_to(Path(name).parts[0])) for name in archive.getnames())
    forbidden = [name for name in names if (
        name.startswith(("private/", "task/public_data/"))
        or Path(name).name in {"target.json", "seed_bank.json"}
        or "__pycache__" in Path(name).parts
    )]
    if forbidden:
        raise AssertionError(f"Distributions contain dataset, gold, or generated caches: {forbidden[:10]}")
    return wheel


def create_data(root: Path) -> None:
    """Invented examples of all schemas, separate from the wheel and checkout."""
    fields_by_schema = {
        "government_id": {
            "full_name": "Example Person", "date_of_birth": "1990-01-01",
            "document_number": "DEMO1234", "issue_date": "2020-01-01",
            "expiry_date": "2030-01-01", "issuing_country": "Canada",
        },
        "proof_of_address": {
            "full_name": "Example Person", "address_line1": "123 Example Avenue",
            "city": "Toronto", "postal_code": "M5V 2T6", "country": "Canada",
            "statement_date": "2026-01-01", "issuer_name": "Example Utilities",
        },
        "payment_receipt": {
            "sender_name": "Example Person", "recipient_name": "Example Company",
            "amount": "100.00", "currency": "CAD", "payment_date": "2026-01-01",
            "reference_id": "DEMO1234",
        },
    }
    gold = root / "private" / "hidden_gold"
    gold.mkdir(parents=True)
    predictions = {}
    for schema, fields in fields_by_schema.items():
        doc_id = f"doc_demo_{schema}"
        document = root / "task" / "public_data" / "val" / doc_id
        hidden = root / "private" / "hidden_test" / doc_id
        document.mkdir(parents=True)
        hidden.mkdir(parents=True)
        target = {"schema_name": schema, "fields": fields}
        files = {
            "meta.json": {"doc_id": doc_id, "schema_name": schema, "num_pages": 1},
            "ocr.json": {"pages": [{"page_index": 0, "tokens": [
                {"text": "Example Person", "line_id": 0, "bbox": [0, 0, 100, 10]}
            ]}]},
            "target.json": target,
        }
        for name, value in files.items():
            (document / name).write_text(json.dumps(value), encoding="utf-8")
            if name != "target.json":
                (hidden / name).write_text(json.dumps(value), encoding="utf-8")
        (gold / f"{doc_id}.json").write_text(json.dumps(target), encoding="utf-8")
        predictions[doc_id] = {"status": "ok", "prediction": target}
    (root / "predictions.json").write_text(json.dumps({
        "version": 1, "documents": predictions,
    }), encoding="utf-8")


def main() -> int:
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "RL_KYC_DATA_ROOT"):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="rl-kyc-wheel-") as tmp:
        temp = Path(tmp)
        dist = temp / "dist"
        run(["uv", "build", "--out-dir", str(dist)], ROOT, env)
        wheel = check_artifacts(dist)
        venv = temp / "venv"
        run(["uv", "venv", "--python", sys.executable, str(venv)], temp, env)
        bindir = venv / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        run(["uv", "pip", "install", "--python", str(python), str(wheel)], temp, env)

        data_root = temp / "external data"
        create_data(data_root)
        env["RL_KYC_DATA_ROOT"] = str(data_root)
        code = """
import json
import sys
from pathlib import Path
import rl_kyc_task_env
from rl_kyc_task_env import DocumentExtractionTask, load_schema, schema_names
from rl_kyc_task_env.paths import REPO_ROOT, RUNTIME_ROOT, SCHEMA_DIR, PROMPT_PATH
assert Path(rl_kyc_task_env.__file__).is_relative_to(Path(sys.prefix))
assert REPO_ROOT != RUNTIME_ROOT
assert SCHEMA_DIR.is_relative_to(Path(sys.prefix))
assert PROMPT_PATH.read_text().strip()
for name in schema_names():
    assert load_schema(name)['title'] == name
task = DocumentExtractionTask(split='val')
assert len(task.records) == 3
record = task.records[0]
observation = task.get_observation(record)
assert observation['doc_id'] == 'doc_demo_government_id'
assert 'gold' not in observation
assert task.score_submission(record, task.load_document(record).gold).reward == 1.0
from generator import utils
assert utils.PUBLIC_VAL_DIR == REPO_ROOT / 'task/public_data/val'
assert utils.HIDDEN_GOLD_DIR == REPO_ROOT / 'private/hidden_gold'
print(json.dumps({'runtime': str(RUNTIME_ROOT), 'data': str(REPO_ROOT)}))
"""
        inspection = json.loads(run([str(python), "-c", code], temp, env).stdout)
        for name in CLI_NAMES:
            help_output = run([str(bindir / name), "--help"], temp, env).stdout
            if "usage:" not in help_output.lower():
                raise AssertionError(f"No usage returned by installed {name}")

        baseline = Path(inspection["runtime"]) / "baselines" / "null_baseline"
        result = json.loads(run(
            [str(bindir / "rl-kyc-public-validator"), str(baseline)], temp, env
        ).stdout)
        if result["num_docs"] != 3 or result["score"] != 0.0:
            raise AssertionError(f"Unexpected installed baseline result: {result}")
        hidden_result = json.loads(run(
            [str(bindir / "rl-kyc-hidden-judge"), "--predictions", str(data_root / "predictions.json")],
            temp, env,
        ).stdout)
        if hidden_result["num_docs"] != 3 or hidden_result["score"] != 1.0:
            raise AssertionError(f"Unexpected installed frozen-prediction score: {hidden_result}")
        print(json.dumps({
            "wheel": wheel.name,
            "wheel_bytes": wheel.stat().st_size,
            "isolated_install": True,
            "external_dataset": True,
            "runtime_schemas": 3,
            "entrypoints_checked": list(CLI_NAMES),
            "baseline_documents": result["num_docs"],
            "baseline_score": result["score"],
            "frozen_prediction_score": hidden_result["score"],
            "api_keys_required": False,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

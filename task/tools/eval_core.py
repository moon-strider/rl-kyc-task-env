from __future__ import annotations

from rl_kyc_task_env.datasets import list_document_dirs, load_json, resolve_gold_path
from rl_kyc_task_env.evaluation import evaluate_document, evaluate_solution
from rl_kyc_task_env.paths import REPO_ROOT, SCHEMA_DIR
from rl_kyc_task_env.runner import TIMEOUT_SECONDS, run_prediction_subprocess
from rl_kyc_task_env.schemas import SCHEMA_NAMES, validate_prediction
from rl_kyc_task_env.scoring import aggregate_scores, score_prediction

score_document = score_prediction

__all__ = [
    "REPO_ROOT",
    "SCHEMA_NAMES",
    "SCHEMA_DIR",
    "TIMEOUT_SECONDS",
    "aggregate_scores",
    "evaluate_document",
    "evaluate_solution",
    "list_document_dirs",
    "load_json",
    "resolve_gold_path",
    "run_prediction_subprocess",
    "score_document",
    "score_prediction",
    "validate_prediction",
]

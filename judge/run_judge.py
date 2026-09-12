from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rl_kyc_task_env.datasets import list_document_dirs
from rl_kyc_task_env.evaluation import evaluate_predictions, evaluate_solution
from rl_kyc_task_env.paths import HIDDEN_GOLD_DIR, HIDDEN_TEST_DIR
from rl_kyc_task_env.prediction_io import load_prediction_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Score frozen predictions, or run an explicitly trusted local baseline.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--predictions", type=Path, help="Bounded version-1 JSON envelope; no code is executed")
    source.add_argument("--trusted-solution", type=Path, help="TRUSTED CODE ONLY: executes locally with access to gold and host files")
    parser.add_argument("--dataset-dir", type=Path, default=HIDDEN_TEST_DIR)
    parser.add_argument("--gold-dir", type=Path, default=HIDDEN_GOLD_DIR)
    args = parser.parse_args()
    if args.predictions is not None:
        doc_ids = {path.name for path in list_document_dirs(args.dataset_dir)}
        envelope = load_prediction_file(args.predictions, doc_ids)
        result = evaluate_predictions(envelope["documents"], args.dataset_dir, args.gold_dir)
    else:
        result = evaluate_solution(args.trusted_solution.resolve(), args.dataset_dir, args.gold_dir)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rl_kyc_task_env.evaluation import evaluate_solution
from rl_kyc_task_env.paths import VAL_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a trusted local solution on public validation documents.")
    parser.add_argument("solution_dir", type=Path)
    parser.add_argument("--dataset-dir", type=Path, default=VAL_DIR)
    args = parser.parse_args()
    result = evaluate_solution(args.solution_dir.resolve(), args.dataset_dir, include_error_summary=True)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from judge.judge_utils import evaluate_solution              


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python judge/run_judge.py <solution_dir>")

    solution_dir = Path(sys.argv[1]).resolve()
    dataset_dir = REPO_ROOT / "private" / "hidden_test"
    gold_dir = REPO_ROOT / "private" / "hidden_gold"
    result = evaluate_solution(solution_dir, dataset_dir, gold_dir)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

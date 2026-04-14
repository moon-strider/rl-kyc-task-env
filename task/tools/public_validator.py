from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task.tools.eval_core import evaluate_solution              


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python task/tools/public_validator.py <solution_dir>")

    solution_dir = Path(sys.argv[1]).resolve()
    dataset_dir = REPO_ROOT / "task" / "public_data" / "val"
    result = evaluate_solution(solution_dir, dataset_dir, include_error_summary=True)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

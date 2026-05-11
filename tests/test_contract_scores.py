from __future__ import annotations

import unittest
from pathlib import Path

from judge.judge_utils import evaluate_solution as evaluate_hidden_solution
from task.tools.eval_core import evaluate_solution


ROOT = Path(__file__).resolve().parents[1]


class ContractScoresTest(unittest.TestCase):
    def test_public_null_baseline_score_stays_zero(self) -> None:
        result = evaluate_solution(
            ROOT / "baselines" / "null_baseline",
            ROOT / "task" / "public_data" / "val",
            include_error_summary=True,
        )
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["num_docs"], 90)

    def test_public_heuristic_baseline_score_stays_fixed(self) -> None:
        result = evaluate_solution(
            ROOT / "baselines" / "heuristic_baseline",
            ROOT / "task" / "public_data" / "val",
            include_error_summary=True,
        )
        self.assertEqual(result["score"], 0.8468)
        self.assertEqual(result["num_docs"], 90)

    def test_hidden_null_baseline_score_stays_zero(self) -> None:
        result = evaluate_hidden_solution(
            ROOT / "baselines" / "null_baseline",
            ROOT / "private" / "hidden_test",
            ROOT / "private" / "hidden_gold",
        )
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["num_docs"], 108)

    def test_hidden_heuristic_baseline_score_stays_fixed(self) -> None:
        result = evaluate_hidden_solution(
            ROOT / "baselines" / "heuristic_baseline",
            ROOT / "private" / "hidden_test",
            ROOT / "private" / "hidden_gold",
        )
        self.assertEqual(result["score"], 0.8296)
        self.assertEqual(result["num_docs"], 108)


if __name__ == "__main__":
    unittest.main()

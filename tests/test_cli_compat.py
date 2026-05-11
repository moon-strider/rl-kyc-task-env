from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliCompatTest(unittest.TestCase):
    def run_cli(self, *args: str) -> dict:
        completed = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_public_validator_cli_accepts_solution_dir(self) -> None:
        result = self.run_cli("task/tools/public_validator.py", "baselines/null_baseline")
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["num_docs"], 90)
        self.assertEqual(result["error_summary"], {})

    def test_hidden_judge_cli_accepts_solution_dir(self) -> None:
        result = self.run_cli("judge/run_judge.py", "baselines/null_baseline")
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["num_docs"], 108)
        self.assertNotIn("error_summary", result)


if __name__ == "__main__":
    unittest.main()

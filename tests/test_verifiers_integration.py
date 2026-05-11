from __future__ import annotations

import asyncio
import unittest

from rl_kyc_task_env.integrations.verifiers import build_dataset_rows, score_completion


class VerifiersIntegrationTest(unittest.TestCase):
    def test_build_dataset_rows_contains_prompts_and_records(self) -> None:
        rows = build_dataset_rows(split="val", limit=2)
        self.assertEqual(len(rows), 2)
        self.assertIn("prompt", rows[0])
        self.assertEqual(rows[0]["prompt"][0]["role"], "user")
        self.assertIn("record_id", rows[0])
        self.assertIn("schema_name", rows[0])

    def test_score_completion_uses_canonical_reward(self) -> None:
        row = build_dataset_rows(split="val", limit=1)[0]
        completion = [{"role": "assistant", "content": row["gold_json"]}]
        reward = asyncio.run(score_completion(completion, row["record_id"], row["split"]))
        self.assertEqual(reward, 1.0)

    def test_load_environment_missing_dependency_is_clear(self) -> None:
        from rl_kyc_task_env.integrations.verifiers import load_environment

        try:
            import verifiers  # noqa: F401
        except ImportError:
            with self.assertRaisesRegex(RuntimeError, "verifiers"):
                load_environment(split="val", limit=1)


if __name__ == "__main__":
    unittest.main()

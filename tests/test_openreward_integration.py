from __future__ import annotations

import unittest

from rl_kyc_task_env.integrations.openreward import OpenRewardKycEnvironment, build_server


class OpenRewardIntegrationTest(unittest.TestCase):
    def test_environment_lists_splits_and_tasks(self) -> None:
        env = OpenRewardKycEnvironment(default_split="val", limit=2)
        self.assertIn("val", env.list_splits())
        tasks = env.list_tasks("val")
        self.assertEqual(len(tasks), 2)
        self.assertIn("doc_id", tasks[0])
        self.assertIn("schema_name", tasks[0])

    def test_environment_prompt_and_tools_use_current_task(self) -> None:
        env = OpenRewardKycEnvironment(default_split="val", limit=1)
        task = env.list_tasks("val")[0]
        prompt = env.get_prompt(task)
        self.assertIn(task["schema_name"], prompt)
        self.assertIn("Return only JSON", prompt)
        self.assertEqual(env.get_metadata(task)["schema_name"], task["schema_name"])
        self.assertIn("properties", env.get_schema(task))
        self.assertGreater(len(env.get_ocr(task)["lines"]), 0)

    def test_submit_extraction_returns_reward_and_finished(self) -> None:
        env = OpenRewardKycEnvironment(default_split="val", limit=1)
        task = env.list_tasks("val")[0]
        document = env.load_task_document(task)
        result = env.submit_extraction(task, document.gold)
        self.assertEqual(result["reward"], 1.0)
        self.assertTrue(result["finished"])
        self.assertEqual(result["status"], "ok")

    def test_build_server_missing_dependency_is_clear(self) -> None:
        try:
            import openreward  # noqa: F401
        except ImportError:
            with self.assertRaisesRegex(RuntimeError, "openreward"):
                build_server(default_split="val", limit=1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rl_kyc_task_env.bundles import build_private_judge_bundle, build_public_bundle
from rl_kyc_task_env.containers import run_hidden_judge, run_public_episode


class ContainerMountsTest(unittest.TestCase):
    def test_public_episode_mounts_package_runtime(self) -> None:
        calls = []

        def fake_run_container(image, mounts, command, timeout_seconds):
            calls.append((mounts, command))
            return subprocess.CompletedProcess(args=[], returncode=0, stdout='{"score": 0.0}', stderr="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            bundle = build_public_bundle(tmp / "public.tar.gz")
            with patch("rl_kyc_task_env.containers.ensure_docker"), patch(
                "rl_kyc_task_env.containers.read_image_metadata",
                return_value={"image": "test", "id": "sha256:test", "repo_digest": None},
            ), patch("rl_kyc_task_env.containers._run_container", side_effect=fake_run_container):
                run_public_episode(bundle, "test", output_dir=tmp / "out")

        validator_mounts = calls[-1][0]
        mounted_paths = {container_path for _, container_path, _ in validator_mounts}
        self.assertIn("/workspace/rl_kyc_task_env", mounted_paths)

    def test_hidden_judge_mounts_package_runtime(self) -> None:
        calls = []

        def fake_run_container(image, mounts, command, timeout_seconds):
            calls.append((mounts, command))
            return subprocess.CompletedProcess(args=[], returncode=0, stdout='{"score": 0.0}', stderr="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            bundle = build_private_judge_bundle(tmp / "private.tar.gz")
            solution_dir = tmp / "solution"
            solution_dir.mkdir()
            (solution_dir / "extract.py").write_text("def predict(document_dir):\n    return {}\n", encoding="utf-8")
            with patch("rl_kyc_task_env.containers.ensure_docker"), patch(
                "rl_kyc_task_env.containers.read_image_metadata",
                return_value={"image": "test", "id": "sha256:test", "repo_digest": None},
            ), patch("rl_kyc_task_env.containers._run_container", side_effect=fake_run_container):
                run_hidden_judge(bundle, "test", solution_dir, output_dir=tmp / "out")

        judge_mounts = calls[-1][0]
        mounted_paths = {container_path for _, container_path, _ in judge_mounts}
        self.assertIn("/workspace/rl_kyc_task_env", mounted_paths)


if __name__ == "__main__":
    unittest.main()

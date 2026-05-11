from __future__ import annotations

import tarfile
import tempfile
import unittest
from pathlib import Path

from harness.artifacts import build_private_judge_bundle, build_public_bundle


class BundlePackageTest(unittest.TestCase):
    def bundle_names(self, path: Path) -> set[str]:
        with tarfile.open(path, "r:gz") as archive:
            return set(archive.getnames())

    def test_public_bundle_contains_package_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_path = build_public_bundle(Path(tmp_dir) / "public.tar.gz")
            names = self.bundle_names(bundle_path)
        self.assertIn("rl_kyc_task_env/evaluation.py", names)
        self.assertIn("rl_kyc_task_env/scoring.py", names)
        self.assertIn("task/tools/public_validator.py", names)

    def test_private_bundle_contains_package_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_path = build_private_judge_bundle(Path(tmp_dir) / "private.tar.gz")
            names = self.bundle_names(bundle_path)
        self.assertIn("rl_kyc_task_env/evaluation.py", names)
        self.assertIn("rl_kyc_task_env/scoring.py", names)
        self.assertIn("judge/run_judge.py", names)


if __name__ == "__main__":
    unittest.main()

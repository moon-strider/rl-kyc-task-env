from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DataRootTest(unittest.TestCase):
    def inspect_paths(self, root: Path | None, cwd: Path) -> dict:
        env = dict(os.environ)
        env.pop("RL_KYC_DATA_ROOT", None)
        env["PYTHONPATH"] = str(ROOT)
        if root is not None:
            env["RL_KYC_DATA_ROOT"] = str(root)
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json; from rl_kyc_task_env.paths import REPO_ROOT, VAL_DIR, "
                "HIDDEN_GOLD_DIR, SCHEMA_DIR, PROMPT_PATH; "
                "from rl_kyc_task_env import load_schema; "
                "print(json.dumps({'root': str(REPO_ROOT), 'val': str(VAL_DIR), "
                "'gold': str(HIDDEN_GOLD_DIR), 'schema_dir': str(SCHEMA_DIR), "
                "'schema': load_schema('government_id')['title'], "
                "'prompt': PROMPT_PATH.read_text()}))",
            ],
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_source_defaults_do_not_depend_on_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inspect_paths(None, Path(tmp))
        self.assertEqual(result["root"], str(ROOT))
        self.assertEqual(result["val"], str(ROOT / "task" / "public_data" / "val"))
        self.assertTrue(result["prompt"].strip())

    def test_external_data_root_cannot_replace_runtime_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "separate dataset"
            schemas = root / "task" / "schemas"
            schemas.mkdir(parents=True)
            (schemas / "government_id.schema.json").write_text("invalid JSON")
            result = self.inspect_paths(root, Path(tmp))
        self.assertEqual(result["root"], str(root))
        self.assertEqual(result["val"], str(root / "task" / "public_data" / "val"))
        self.assertEqual(result["gold"], str(root / "private" / "hidden_gold"))
        self.assertEqual(result["schema_dir"], str(ROOT / "task" / "schemas"))
        self.assertEqual(result["schema"], "government_id")


if __name__ == "__main__":
    unittest.main()

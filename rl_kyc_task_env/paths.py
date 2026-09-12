from __future__ import annotations

import os
from pathlib import Path

# Installed runtime resources are independent of datasets. Set RL_KYC_DATA_ROOT
# before importing the package to use a dataset checkout outside site-packages.
RUNTIME_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(os.environ.get("RL_KYC_DATA_ROOT", str(RUNTIME_ROOT))).expanduser().resolve()
TASK_DIR = REPO_ROOT / "task"
PUBLIC_DATA_DIR = TASK_DIR / "public_data"
PRIVATE_DIR = REPO_ROOT / "private"
SCHEMA_DIR = RUNTIME_ROOT / "task" / "schemas"
PROMPT_PATH = RUNTIME_ROOT / "task" / "prompt.txt"
TRAIN_DIR = PUBLIC_DATA_DIR / "train"
VAL_DIR = PUBLIC_DATA_DIR / "val"
HIDDEN_TEST_DIR = PRIVATE_DIR / "hidden_test"
HIDDEN_GOLD_DIR = PRIVATE_DIR / "hidden_gold"

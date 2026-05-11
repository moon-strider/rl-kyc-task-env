from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = REPO_ROOT / "task"
PUBLIC_DATA_DIR = TASK_DIR / "public_data"
PRIVATE_DIR = REPO_ROOT / "private"
SCHEMA_DIR = TASK_DIR / "schemas"
PROMPT_PATH = TASK_DIR / "prompt.txt"
TRAIN_DIR = PUBLIC_DATA_DIR / "train"
VAL_DIR = PUBLIC_DATA_DIR / "val"
HIDDEN_TEST_DIR = PRIVATE_DIR / "hidden_test"
HIDDEN_GOLD_DIR = PRIVATE_DIR / "hidden_gold"

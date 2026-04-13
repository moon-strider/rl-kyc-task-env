"""Shared generator utilities: seeding, paths, serialization, document writing."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------
PUBLIC_SEED: int = 20260413
HIDDEN_SEED: int = 90731157


def make_rng(seed: int) -> np.random.Generator:
    """Return a seeded numpy Generator."""
    return np.random.default_rng(seed)


def seed_python_random(seed: int) -> None:
    """Seed the stdlib random module."""
    random.seed(seed)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

PUBLIC_TRAIN_DIR = REPO_ROOT / "task" / "public_data" / "train"
PUBLIC_VAL_DIR = REPO_ROOT / "task" / "public_data" / "val"
HIDDEN_TEST_DIR = REPO_ROOT / "private" / "hidden_test"


def split_output_dir(split: str) -> Path:
    """Return the root output directory for the given split name."""
    mapping = {
        "train": PUBLIC_TRAIN_DIR,
        "val": PUBLIC_VAL_DIR,
        "hidden_test": HIDDEN_TEST_DIR,
    }
    if split not in mapping:
        raise ValueError(f"Unknown split: {split!r}")
    return mapping[split]


def doc_dir(output_root: Path, doc_id: str) -> Path:
    """Return (and create) the directory for a single document."""
    d = output_root / doc_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "pages").mkdir(exist_ok=True)
    return d


def format_doc_id(index: int) -> str:
    """Return a zero-padded document ID string."""
    return f"doc_{index:06d}"


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def write_json(path: Path, obj: Any, indent: int = 2) -> None:
    """Write *obj* as pretty-printed JSON to *path*."""
    path.write_text(json.dumps(obj, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Document artifact writers
# ---------------------------------------------------------------------------
def write_meta(doc_path: Path, doc_id: str, schema_name: str) -> None:
    """Write meta.json for a document."""
    write_json(
        doc_path / "meta.json",
        {
            "doc_id": doc_id,
            "schema_name": schema_name,
            "num_pages": 1,
            "language": "en",
        },
    )


def write_ocr(doc_path: Path, tokens: list[dict]) -> None:
    """Write ocr.json for a single-page document."""
    write_json(
        doc_path / "ocr.json",
        {
            "pages": [
                {
                    "page_index": 0,
                    "width": 1600,
                    "height": 2200,
                    "tokens": tokens,
                }
            ]
        },
    )


def write_page_image(doc_path: Path, image: Image.Image) -> None:
    """Save the rendered page PNG."""
    image.save(str(doc_path / "pages" / "0.png"), format="PNG")


def write_target(doc_path: Path, schema_name: str, fields: dict) -> None:
    """Write target.json (only for public train/val documents)."""
    write_json(
        doc_path / "target.json",
        {"schema_name": schema_name, "fields": fields},
    )


# ---------------------------------------------------------------------------
# Deterministic integer drawing without touching the Generator state for Faker
# ---------------------------------------------------------------------------
def rng_choice(rng: np.random.Generator, items: list) -> Any:
    """Pick one item from *items* using *rng*."""
    idx = int(rng.integers(0, len(items)))
    return items[idx]


def rng_randint(rng: np.random.Generator, low: int, high: int) -> int:
    """Return a random int in [low, high] inclusive."""
    return int(rng.integers(low, high + 1))


def rng_uniform(rng: np.random.Generator, low: float, high: float) -> float:
    """Return a random float in [low, high)."""
    return float(rng.uniform(low, high))

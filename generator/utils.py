                                                                                  

from __future__ import annotations

import json
import os
import random
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

                                                                             
       
                                                                             
PUBLIC_SEED: int = 20260413
HIDDEN_SEED: int = 90731157


def make_rng(seed: int) -> np.random.Generator:
                                          
    return np.random.default_rng(seed)


def seed_python_random(seed: int) -> None:
                                        
    random.seed(seed)


                                                                             
              
                                                                             
REPO_ROOT = Path(__file__).resolve().parent.parent

PUBLIC_TRAIN_DIR = REPO_ROOT / "task" / "public_data" / "train"
PUBLIC_VAL_DIR = REPO_ROOT / "task" / "public_data" / "val"
HIDDEN_TEST_DIR = REPO_ROOT / "private" / "hidden_test"
HIDDEN_GOLD_DIR = REPO_ROOT / "private" / "hidden_gold"
SEED_BANK_PATH = REPO_ROOT / "private" / "seed_bank.json"


def split_output_dir(split: str) -> Path:
                                                                    
    mapping = {
        "train": PUBLIC_TRAIN_DIR,
        "val": PUBLIC_VAL_DIR,
        "hidden_test": HIDDEN_TEST_DIR,
    }
    if split not in mapping:
        raise ValueError(f"Unknown split: {split!r}")
    return mapping[split]


def doc_dir(output_root: Path, doc_id: str) -> Path:
                                                                  
    d = output_root / doc_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "pages").mkdir(exist_ok=True)
    return d


def reset_output_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def format_doc_id(index: int) -> str:
                                                  
    return f"doc_{index:06d}"


                                                                             
              
                                                                             
def write_json(path: Path, obj: Any, indent: int = 2) -> None:
                                                       
    path.write_text(json.dumps(obj, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


                                                                             
                           
                                                                             
def write_meta(doc_path: Path, doc_id: str, schema_name: str) -> None:
                                         
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
                                     
    image.save(str(doc_path / "pages" / "0.png"), format="PNG")


def write_target(doc_path: Path, schema_name: str, fields: dict) -> None:
                                                                  
    write_json(
        doc_path / "target.json",
        {"schema_name": schema_name, "fields": fields},
    )


def write_hidden_gold(gold_root: Path, doc_id: str, schema_name: str, fields: dict) -> None:
    gold_root.mkdir(parents=True, exist_ok=True)
    write_json(
        gold_root / f"{doc_id}.json",
        {"schema_name": schema_name, "fields": fields},
    )


                                                                             
                                                                              
                                                                             
def rng_choice(rng: np.random.Generator, items: list) -> Any:
                                                 
    idx = int(rng.integers(0, len(items)))
    return items[idx]


def rng_randint(rng: np.random.Generator, low: int, high: int) -> int:
                                                       
    return int(rng.integers(low, high + 1))


def rng_uniform(rng: np.random.Generator, low: float, high: float) -> float:
                                               
    return float(rng.uniform(low, high))

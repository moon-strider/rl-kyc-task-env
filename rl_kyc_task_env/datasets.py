from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import HIDDEN_GOLD_DIR, HIDDEN_TEST_DIR, TRAIN_DIR, VAL_DIR
from .records import Document, DocumentRecord, SplitPaths


def load_json(path: Path | None) -> Any:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_split_paths(split: str) -> SplitPaths:
    if split == "train":
        return SplitPaths(split=split, dataset_dir=TRAIN_DIR)
    if split == "val":
        return SplitPaths(split=split, dataset_dir=VAL_DIR)
    if split == "hidden_test":
        return SplitPaths(split=split, dataset_dir=HIDDEN_TEST_DIR, gold_dir=HIDDEN_GOLD_DIR)
    raise ValueError(f"Unknown split: {split}")


def list_document_dirs(dataset_dir: Path) -> list[Path]:
    if not dataset_dir.exists():
        return []
    return sorted(path for path in dataset_dir.iterdir() if path.is_dir())


def resolve_gold_path(document_dir: Path, gold_dir: Path | None = None) -> Path:
    target_path = document_dir / "target.json" if gold_dir is None else gold_dir / f"{document_dir.name}.json"
    if target_path.exists():
        return target_path
    raise FileNotFoundError(f"Could not locate gold target for {document_dir}")


def build_record(document_dir: Path, split: str, gold_dir: Path | None = None) -> DocumentRecord:
    meta = load_json(document_dir / "meta.json")
    gold_path = resolve_gold_path(document_dir, gold_dir)
    return DocumentRecord(
        doc_id=meta["doc_id"],
        schema_name=meta["schema_name"],
        split=split,
        document_dir=document_dir,
        gold_path=gold_path,
        meta=meta,
    )


def list_documents(
    split: str,
    limit: int | None = None,
    indices: list[int] | tuple[int, ...] | None = None,
    schemas: list[str] | tuple[str, ...] | None = None,
) -> list[DocumentRecord]:
    paths = get_split_paths(split)
    document_dirs = list_document_dirs(paths.dataset_dir)
    if indices is not None:
        document_dirs = [document_dirs[index] for index in indices]
    records = [build_record(path, split, paths.gold_dir) for path in document_dirs]
    if schemas is not None:
        schema_set = set(schemas)
        records = [record for record in records if record.schema_name in schema_set]
    if limit is not None:
        records = records[:limit]
    return records


def load_document(record: DocumentRecord) -> Document:
    return Document(
        record=record,
        meta=load_json(record.document_dir / "meta.json"),
        ocr=load_json(record.document_dir / "ocr.json"),
        gold=load_json(record.gold_path),
    )

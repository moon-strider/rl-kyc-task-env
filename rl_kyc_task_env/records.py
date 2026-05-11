from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SplitPaths:
    split: str
    dataset_dir: Path
    gold_dir: Path | None = None


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    schema_name: str
    split: str
    document_dir: Path
    gold_path: Path | None
    meta: dict[str, Any]


@dataclass(frozen=True)
class Document:
    record: DocumentRecord
    meta: dict[str, Any]
    ocr: dict[str, Any]
    gold: dict[str, Any] | None


@dataclass(frozen=True)
class PredictionResult:
    status: str
    prediction: Any | None


@dataclass(frozen=True)
class SubmissionScore:
    schema_name: str
    score: float
    status: str
    reward: float
    prediction: dict[str, Any] | None = None

from __future__ import annotations

import json
from typing import Any

from rl_kyc_task_env.datasets import list_documents, load_document
from rl_kyc_task_env.environment import DocumentExtractionTask
from rl_kyc_task_env.prompts import build_document_prompt


def build_dataset_rows(
    split: str = "train",
    limit: int | None = None,
    indices: list[int] | tuple[int, ...] | None = None,
    schemas: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for index, record in enumerate(list_documents(split, limit=limit, indices=indices, schemas=schemas)):
        document = load_document(record)
        rows.append(
            {
                "prompt": [{"role": "user", "content": build_document_prompt(record)}],
                "record_id": record.doc_id,
                "record_index": index,
                "split": split,
                "schema_name": record.schema_name,
                "gold_json": json.dumps(document.gold, ensure_ascii=False, sort_keys=True),
            }
        )
    return rows


async def score_completion(completion: list[dict[str, Any]], record_id: str, split: str) -> float:
    task = DocumentExtractionTask(split=split)
    records = [record for record in task.records if record.doc_id == record_id]
    if not records:
        return 0.0
    last = completion[-1] if completion else {}
    content = last.get("content", "") if isinstance(last, dict) else ""
    return task.evaluate_text_submission(records[0], str(content)).reward


def load_environment(
    split: str = "train",
    limit: int | None = None,
    indices: list[int] | tuple[int, ...] | None = None,
    schemas: list[str] | tuple[str, ...] | None = None,
    mode: str = "single_turn",
) -> Any:
    if mode != "single_turn":
        raise ValueError(f"Unsupported Verifiers mode: {mode}")
    try:
        import verifiers as vf
    except ImportError as exc:
        raise RuntimeError("install verifiers to use rl-kyc-task-env Verifiers integration") from exc
    rows = build_dataset_rows(split=split, limit=limit, indices=indices, schemas=schemas)
    try:
        from datasets import Dataset
    except ImportError:
        dataset = rows
    else:
        dataset = Dataset.from_list(rows)

    async def reward(completion: list[dict[str, Any]], record_id: str, split: str) -> float:
        return await score_completion(completion, record_id, split)

    rubric = vf.Rubric(funcs=[reward])
    return vf.SingleTurnEnv(dataset=dataset, rubric=rubric)

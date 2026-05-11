from __future__ import annotations

from typing import Any

from rl_kyc_task_env.datasets import list_documents, load_document
from rl_kyc_task_env.environment import DocumentExtractionTask
from rl_kyc_task_env.prompts import build_document_prompt, reconstruct_ocr_lines
from rl_kyc_task_env.schemas import field_names, load_schema


class OpenRewardKycEnvironment:
    name = "rl-kyc-task-env"

    def __init__(self, default_split: str = "train", limit: int | None = None) -> None:
        self.default_split = default_split
        self.limit = limit

    def list_splits(self) -> list[str]:
        return ["train", "val", "hidden_test"]

    def list_tasks(self, split: str | None = None) -> list[dict[str, Any]]:
        selected_split = split or self.default_split
        records = list_documents(selected_split, limit=self.limit)
        return [
            {
                "doc_id": record.doc_id,
                "schema_name": record.schema_name,
                "split": selected_split,
                "index": index,
            }
            for index, record in enumerate(records)
        ]

    def record_for_task(self, task: dict[str, Any]) -> Any:
        split = task.get("split", self.default_split)
        doc_id = task["doc_id"]
        records = list_documents(split)
        for record in records:
            if record.doc_id == doc_id:
                return record
        raise KeyError(doc_id)

    def load_task_document(self, task: dict[str, Any]) -> Any:
        return load_document(self.record_for_task(task))

    def get_prompt(self, task: dict[str, Any]) -> str:
        return build_document_prompt(self.record_for_task(task))

    def get_metadata(self, task: dict[str, Any]) -> dict[str, Any]:
        return self.load_task_document(task).meta

    def get_schema(self, task: dict[str, Any]) -> dict[str, Any]:
        return load_schema(task["schema_name"])

    def get_ocr(self, task: dict[str, Any], raw: bool = False) -> dict[str, Any]:
        document = self.load_task_document(task)
        if raw:
            return document.ocr
        return {"lines": reconstruct_ocr_lines(document.ocr)}

    def get_page_image_info(self, task: dict[str, Any]) -> dict[str, Any]:
        record = self.record_for_task(task)
        page_path = record.document_dir / "pages" / "0.png"
        return {"path": str(page_path), "page_index": 0, "exists": page_path.exists()}

    def submit_extraction(self, task: dict[str, Any], prediction: Any) -> dict[str, Any]:
        record = self.record_for_task(task)
        env = DocumentExtractionTask(split=task.get("split", self.default_split))
        result = env.score_submission(record, prediction)
        return {
            "reward": result.reward,
            "finished": True,
            "status": result.status,
            "score": result.score,
            "schema_name": result.schema_name,
        }

    def task_tools(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "metadata": self.get_metadata(task),
            "schema": self.get_schema(task),
            "fields": field_names(task["schema_name"]),
            "ocr": self.get_ocr(task),
            "page_image": self.get_page_image_info(task),
        }


def build_server(default_split: str = "train", limit: int | None = None) -> Any:
    try:
        from openreward import Server
    except ImportError as exc:
        raise RuntimeError("install openreward to use rl-kyc-task-env OpenReward integration") from exc
    environment = OpenRewardKycEnvironment(default_split=default_split, limit=limit)
    return Server(environment)

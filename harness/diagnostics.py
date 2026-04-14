from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_output(raw: str) -> dict[str, Any]:
    return json.loads(raw)


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_summary(path: Path, title: str, payload: dict[str, Any]) -> Path:
    lines = [
        title,
        f"score: {payload.get('score')}",
        f"by_schema: {json.dumps(payload.get('by_schema', {}), ensure_ascii=False)}",
        f"num_docs: {payload.get('num_docs')}",
    ]
    error_summary = payload.get("error_summary")
    if error_summary is not None:
        lines.append(f"error_summary: {json.dumps(error_summary, ensure_ascii=False)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

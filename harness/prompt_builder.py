from __future__ import annotations

import json
from pathlib import Path


def build_agent_context(bundle_root: Path) -> str:
    task_dir = bundle_root / "task"
    sections = [
        "# Agent Context",
        "",
        "## Task README",
        task_dir.joinpath("README.md").read_text(encoding="utf-8").strip(),
        "",
        "## Task Prompt",
        task_dir.joinpath("prompt.txt").read_text(encoding="utf-8").strip(),
        "",
        "## Schemas",
    ]
    for schema_path in sorted(task_dir.joinpath("schemas").glob("*.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        sections.extend(
            [
                "",
                f"### {schema_path.name}",
                "```json",
                json.dumps(schema, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    return "\n".join(sections) + "\n"


def write_agent_context(bundle_root: Path) -> Path:
    path = bundle_root / "AGENT_CONTEXT.md"
    path.write_text(build_agent_context(bundle_root), encoding="utf-8")
    return path

from __future__ import annotations

from typing import Any

from .datasets import load_document
from .records import DocumentRecord
from .schemas import field_names


def reconstruct_ocr_lines(ocr: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for page in ocr.get("pages", []):
        page_index = page.get("page_index", 0)
        for token in page.get("tokens", []):
            key = (page_index, token.get("line_id", 0))
            grouped.setdefault(key, []).append(token)
    lines = []
    for (page_index, line_id), tokens in sorted(grouped.items()):
        ordered = sorted(tokens, key=lambda token: (token.get("bbox", [0, 0, 0, 0])[0], token.get("text", "")))
        text = " ".join(str(token.get("text", "")) for token in ordered).strip()
        boxes = [token.get("bbox", [0, 0, 0, 0]) for token in ordered]
        if boxes:
            bbox = [
                min(box[0] for box in boxes),
                min(box[1] for box in boxes),
                max(box[2] for box in boxes),
                max(box[3] for box in boxes),
            ]
        else:
            bbox = [0, 0, 0, 0]
        lines.append({"page_index": page_index, "line_id": line_id, "text": text, "bbox": bbox})
    return lines


def build_document_prompt(record: DocumentRecord) -> str:
    document = load_document(record)
    lines = reconstruct_ocr_lines(document.ocr)
    rendered_lines = "\n".join(line["text"] for line in lines)
    fields = "\n".join(f"- {name}" for name in field_names(record.schema_name))
    return (
        "You are extracting structured fields from one document.\n"
        f"Document id: {record.doc_id}\n"
        f"Schema: {record.schema_name}\n"
        "Fields:\n"
        f"{fields}\n\n"
        "OCR lines:\n"
        f"{rendered_lines}\n\n"
        "Return only JSON with keys schema_name and fields."
    )

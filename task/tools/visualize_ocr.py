from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

DEFAULT_BOX_COLOR = (255, 0, 0)
DEFAULT_TEXT_COLOR = (0, 0, 255)


def load_ocr_tokens(document_dir: Path) -> tuple[Path, list[dict]]:
    image_path = document_dir / "pages" / "0.png"
    ocr_path = document_dir / "ocr.json"
    with ocr_path.open("r", encoding="utf-8") as handle:
        ocr = json.load(handle)
    pages = ocr.get("pages", [])
    if not pages:
        raise ValueError(f"No OCR pages found in {ocr_path}")
    return image_path, pages[0].get("tokens", [])


def draw_overlay(document_dir: Path, output_path: Path) -> Path:
    image_path, tokens = load_ocr_tokens(document_dir)
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    for token in tokens:
        bbox = token.get("bbox")
        text = token.get("text", "")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        draw.rectangle((x1, y1, x2, y2), outline=DEFAULT_BOX_COLOR, width=2)
        label_y = max(0, y1 - 14)
        draw.text((x1, label_y), str(text), fill=DEFAULT_TEXT_COLOR)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        raise SystemExit(
            "Usage: python task/tools/visualize_ocr.py <document_dir> [output_path]"
        )

    document_dir = Path(sys.argv[1]).resolve()
    if len(sys.argv) == 3:
        output_path = Path(sys.argv[2]).resolve()
    else:
        output_path = document_dir / "ocr_overlay.png"

    saved_path = draw_overlay(document_dir, output_path)
    sys.stdout.write(f"{saved_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

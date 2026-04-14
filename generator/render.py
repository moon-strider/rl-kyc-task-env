"""Rendering engine: convert a list of render elements to a PNG image.

Returns:
  - A clean Pillow Image (1600 x 2200, white background)
  - A list of ground-truth box dicts: {text, x1, y1, x2, y2, is_label, block_id}

The renderer tries to load a TrueType font from common system paths.
If none are found it falls back to Pillow's built-in bitmap font.

Element dict schema (from template_specs_*.py):
  text       : str
  x          : int   — left edge (for left-anchored text) or center x (for centered)
  y          : int   — top edge
  font_size  : int
  is_label   : bool
  block_id   : int
  bold       : bool

Special text value "__HLINE__" draws a horizontal rule across the page.
Special text value "__CENTER__" prefix causes centered rendering (set in
template functions by passing x = W // 2).

Centering heuristic: if x == W // 2 (800) the text is centered on that x.
"""

from __future__ import annotations

import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PAGE_W = 1600
PAGE_H = 2200
BG_COLOR = (255, 255, 255)
TEXT_COLOR = (20, 20, 20)
HLINE_COLOR = (80, 80, 80)

CENTER_X = PAGE_W // 2  # 800 — sentinel for centering

# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------
_FONT_CANDIDATES_REGULAR = [
    # Linux (DejaVu — most common in Docker/CI)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    # macOS
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    # Windows
    "C:/Windows/Fonts/arial.ttf",
    # Generic fallback paths
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

_FONT_PATH_REGULAR: Optional[str] = None
_FONT_PATH_BOLD: Optional[str] = None

def _find_font(candidates: list[str]) -> Optional[str]:
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _resolve_fonts() -> None:
    global _FONT_PATH_REGULAR, _FONT_PATH_BOLD
    _FONT_PATH_REGULAR = _find_font(_FONT_CANDIDATES_REGULAR)
    _FONT_PATH_BOLD = _find_font(_FONT_CANDIDATES_BOLD) or _FONT_PATH_REGULAR


_resolve_fonts()


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load and return a font of the given size."""
    path = _FONT_PATH_BOLD if (bold and _FONT_PATH_BOLD) else _FONT_PATH_REGULAR
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    # Fallback: Pillow built-in default (supports size= in Pillow >= 10)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Text measurement helpers
# ---------------------------------------------------------------------------

def _measure_text(text: str, font: ImageFont.ImageFont) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) bbox of text relative to draw origin."""
    try:
        return font.getbbox(text)
    except AttributeError:
        # Older Pillow
        w, h = font.getsize(text)
        return (0, 0, w, h)


def _text_width(text: str, font: ImageFont.ImageFont) -> int:
    l, t, r, b = _measure_text(text, font)
    return r - l


def _text_height(text: str, font: ImageFont.ImageFont) -> int:
    l, t, r, b = _measure_text(text, font)
    return b - t


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_document(elements: list[dict]) -> tuple[Image.Image, list[dict]]:
    """Render *elements* onto a 1600×2200 white page.

    Returns:
      (image, boxes) where boxes is a list of:
        {text, x1, y1, x2, y2, is_label, block_id}
      Boxes are not yet sorted — sorting happens in ocr_noise.py.
    """
    img = Image.new("RGB", (PAGE_W, PAGE_H), BG_COLOR)
    draw = ImageDraw.Draw(img)
    boxes: list[dict] = []

    for el in elements:
        kind = el.get("kind", "text")
        if kind == "rect":
            draw.rectangle(
                (el["x1"], el["y1"], el["x2"], el["y2"]),
                fill=el.get("fill"),
                outline=el.get("outline"),
                width=el.get("width", 1),
            )
            continue
        if kind == "line":
            draw.line(
                [(el["x1"], el["y1"]), (el["x2"], el["y2"])],
                fill=el.get("fill", HLINE_COLOR),
                width=el.get("width", 2),
            )
            continue

        text = el["text"]
        x = el["x"]
        y = el["y"]
        font_size = el.get("font_size", 30)
        is_label = el.get("is_label", False)
        block_id = el.get("block_id", 0)
        bold = el.get("bold", False)
        fill_value = el.get("fill")
        fill = TEXT_COLOR if fill_value is None else tuple(fill_value)

        font = _get_font(font_size, bold=bold)
        bbox_rel = _measure_text(text, font)
        w = bbox_rel[2] - bbox_rel[0]

        if x == CENTER_X:
            draw_x = x - w // 2 - bbox_rel[0]
        else:
            draw_x = x - bbox_rel[0]

        draw_y = y - bbox_rel[1]

        x1 = draw_x + bbox_rel[0]
        y1 = draw_y + bbox_rel[1]
        x2 = draw_x + bbox_rel[2]
        y2 = draw_y + bbox_rel[3]

        x1 = max(0, min(x1, PAGE_W))
        y1 = max(0, min(y1, PAGE_H))
        x2 = max(0, min(x2, PAGE_W))
        y2 = max(0, min(y2, PAGE_H))

        if x2 <= x1 or y2 <= y1:
            continue

        draw.text((draw_x, draw_y), text, font=font, fill=fill)

        boxes.append({
            "text": text,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "is_label": is_label,
            "block_id": block_id,
        })

    return img, boxes

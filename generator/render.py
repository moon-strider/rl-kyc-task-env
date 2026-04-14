\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
\
   

from __future__ import annotations

import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

                                                                             
           
                                                                             
PAGE_W = 1600
PAGE_H = 2200
BG_COLOR = (255, 255, 255)
TEXT_COLOR = (20, 20, 20)
HLINE_COLOR = (80, 80, 80)

CENTER_X = PAGE_W // 2                                

                                                                             
              
                                                                             
_FONT_CANDIDATES_REGULAR = [
                                               
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
           
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
             
    "C:/Windows/Fonts/arial.ttf",
                            
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
                                                   
    path = _FONT_PATH_BOLD if (bold and _FONT_PATH_BOLD) else _FONT_PATH_REGULAR
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
                                                                        
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


                                                                             
                          
                                                                             

def _measure_text(text: str, font: ImageFont.ImageFont) -> tuple[int, int, int, int]:
                                                                                 
    try:
        return font.getbbox(text)
    except AttributeError:
                      
        w, h = font.getsize(text)
        return (0, 0, w, h)


def _text_width(text: str, font: ImageFont.ImageFont) -> int:
    l, t, r, b = _measure_text(text, font)
    return r - l


def _text_height(text: str, font: ImageFont.ImageFont) -> int:
    l, t, r, b = _measure_text(text, font)
    return b - t


                                                                             
                      
                                                                             

def render_document(elements: list[dict]) -> tuple[Image.Image, list[dict]]:
\
\
\
\
\
\
       
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

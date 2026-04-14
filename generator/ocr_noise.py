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

import re
import unicodedata
from typing import Any

import numpy as np

from generator.utils import rng_uniform, rng_randint, rng_choice

                                                                             
                                         
                                                                             
_CONFUSION_MAP: dict[str, str] = {
    "O": "0", "0": "O",
    "I": "1", "1": "I",
    "l": "1",
    "S": "5", "5": "S",
    "B": "8", "8": "B",
}


def _confuse_char(ch: str, rng: np.random.Generator, rate: float) -> str:
                                                         
    if rng.random() < rate and ch in _CONFUSION_MAP:
        return _CONFUSION_MAP[ch]
    return ch


def _corrupt_text(text: str, rng: np.random.Generator, is_label: bool) -> str:
                                                    
    rate = 0.005 if is_label else 0.015
    return "".join(_confuse_char(c, rng, rate) for c in text)


                                                                             
                                                        
                                                                             

def _split_into_word_tokens(
    box: dict, rng: np.random.Generator
) -> list[dict]:
\
\
\
       
    text = box["text"].strip()
    if not text:
        return []

    words = text.split()
    if not words:
        return []

    x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
    total_chars = sum(len(w) for w in words)
    total_width = x2 - x1

                                                                 
    n_gaps = len(words) - 1
                                                    
    if total_chars > 0:
        char_width = total_width / (total_chars + 0.5 * n_gaps)
    else:
        char_width = total_width / max(len(words), 1)
    space_width = char_width * 0.5

    tokens: list[dict] = []
    cursor = x1
    for i, word in enumerate(words):
        w = len(word) * char_width
        tok_x1 = int(cursor)
        tok_x2 = int(cursor + w)
        tok_x2 = min(tok_x2, x2)
        tokens.append({
            "text": word,
            "x1": tok_x1,
            "y1": y1,
            "x2": tok_x2,
            "y2": y2,
            "is_label": box["is_label"],
            "block_id": box["block_id"],
        })
        cursor += w + space_width

    return tokens


                                                                             
             
                                                                             

def _sort_key(tok: dict) -> tuple:
                                                    
                                                           
    cy = (tok["y1"] + tok["y2"]) / 2
    cx = (tok["x1"] + tok["x2"]) / 2
    return (cy, cx)


                                                                             
                      
                                                                             

def _assign_line_ids(tokens: list[dict]) -> list[dict]:
\
\
\
\
       
    if not tokens:
        return tokens

                                  
    heights = [(t["y2"] - t["y1"]) for t in tokens]
    avg_h = max(sum(heights) / len(heights), 8)
    threshold = avg_h * 0.6

    line_id = 0
    prev_cy = (tokens[0]["y1"] + tokens[0]["y2"]) / 2

    for tok in tokens:
        cy = (tok["y1"] + tok["y2"]) / 2
        if abs(cy - prev_cy) > threshold:
            line_id += 1
            prev_cy = cy
        tok["line_id"] = line_id

    return tokens


                                                                             
                     
                                                                             

def apply_ocr_noise(
    boxes: list[dict],
    rng: np.random.Generator,
) -> list[dict]:
                                                                            

                                                                          
                                          
                                                                          
    raw_tokens: list[dict] = []
    for box in boxes:
        raw_tokens.extend(_split_into_word_tokens(box, rng))

    if not raw_tokens:
        return []

                                                                          
                                                   
                                                                          
    raw_tokens.sort(key=_sort_key)

                                                                          
                            
                                                                          
    raw_tokens = _assign_line_ids(raw_tokens)

                                                                          
                                              
                                                                          
    for tok in raw_tokens:
        for coord in ("x1", "y1", "x2", "y2"):
            jitter = int(rng.integers(-2, 3))                   
            tok[coord] = max(0, tok[coord] + jitter)

                                                                          
                                 
                                                                          
    for tok in raw_tokens:
        tok["text"] = _corrupt_text(tok["text"], rng, tok["is_label"])

                                                                          
                             
                                                                          
    kept: list[dict] = []
    for tok in raw_tokens:
        if rng.random() < 0.01:
            continue        
        kept.append(tok)
    raw_tokens = kept

                                                                          
                                                          
                                                                          
    merged: list[dict] = []
    i = 0
    while i < len(raw_tokens):
        tok = raw_tokens[i]
        if (
            i + 1 < len(raw_tokens)
            and raw_tokens[i + 1]["line_id"] == tok["line_id"]
            and rng.random() < 0.04
        ):
            nxt = raw_tokens[i + 1]
            merged_tok = {
                "text": tok["text"] + nxt["text"],
                "x1": min(tok["x1"], nxt["x1"]),
                "y1": min(tok["y1"], nxt["y1"]),
                "x2": max(tok["x2"], nxt["x2"]),
                "y2": max(tok["y2"], nxt["y2"]),
                "is_label": tok["is_label"],
                "block_id": tok["block_id"],
                "line_id": tok["line_id"],
            }
            merged.append(merged_tok)
            i += 2
        else:
            merged.append(tok)
            i += 1
    raw_tokens = merged

                                                                          
                                                            
                                                                          
    split_tokens: list[dict] = []
    for tok in raw_tokens:
        text = tok["text"]
        if len(text) > 6 and rng.random() < 0.03:
            mid = len(text) // 2
            left_text = text[:mid]
            right_text = text[mid:]
            total_w = tok["x2"] - tok["x1"]
            split_x = tok["x1"] + int(total_w * mid / len(text))
            split_tokens.append({
                "text": left_text,
                "x1": tok["x1"], "y1": tok["y1"],
                "x2": split_x, "y2": tok["y2"],
                "is_label": tok["is_label"],
                "block_id": tok["block_id"],
                "line_id": tok["line_id"],
            })
            split_tokens.append({
                "text": right_text,
                "x1": split_x, "y1": tok["y1"],
                "x2": tok["x2"], "y2": tok["y2"],
                "is_label": tok["is_label"],
                "block_id": tok["block_id"],
                "line_id": tok["line_id"],
            })
        else:
            split_tokens.append(tok)
    raw_tokens = split_tokens

                                                                          
                                                                   
                                                                          
                            
    label_line_ids = {tok["line_id"] for tok in raw_tokens if tok["is_label"]}
                                                    
    lines_to_cap = {
        lid for lid in label_line_ids if rng.random() < 0.10
    }
    for tok in raw_tokens:
        if tok["line_id"] in lines_to_cap:
            tok["text"] = tok["text"].upper()

                                                                          
                                                            
                                                                          
    raw_tokens.sort(key=_sort_key)

                                                                          
                                                                           
                                                                          
    ocr_tokens: list[dict] = []
    for tok in raw_tokens:
        if not tok["text"].strip():
            continue
        conf = float(rng.uniform(0.82, 0.99))
        x1 = tok["x1"]
        y1 = tok["y1"]
        x2 = max(tok["x2"], x1 + 1)
        y2 = max(tok["y2"], y1 + 1)
        ocr_tokens.append({
            "text": tok["text"],
            "bbox": [x1, y1, x2, y2],
            "line_id": tok["line_id"],
            "block_id": tok["block_id"],
            "conf": round(conf, 4),
        })

    return ocr_tokens

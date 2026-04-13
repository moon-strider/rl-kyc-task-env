"""OCR noise pipeline.

Input:  ground-truth boxes from render.py —
        list of {text, x1, y1, x2, y2, is_label, block_id}

Output: OCR token list for ocr.json —
        list of {text, bbox, line_id, block_id, conf}

Pipeline:
  1. Split each box into word tokens, computing sub-bboxes proportionally.
  2. Sort all tokens top-to-bottom then left-to-right.
  3. Assign line_id (unique per visual line) and block_id.
  4. Apply bbox jitter ±2 px per coordinate.
  5. Apply char confusion: 1.5% for value tokens, 0.5% for label tokens.
  6. Apply token drop: 1%.
  7. Apply token merge: 4% of adjacent same-line pairs.
  8. Apply token split: 3% of tokens longer than 6 characters.
  9. Apply random label-line capitalization: 10% of label lines.
 10. Sample confidence uniformly in [0.82, 0.99].
 11. Re-sort final token list top-to-bottom then left-to-right.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import numpy as np

from generator.utils import rng_uniform, rng_randint, rng_choice

# ---------------------------------------------------------------------------
# Character confusion map (bidirectional)
# ---------------------------------------------------------------------------
_CONFUSION_MAP: dict[str, str] = {
    "O": "0", "0": "O",
    "I": "1", "1": "I",
    "l": "1",
    "S": "5", "5": "S",
    "B": "8", "8": "B",
}


def _confuse_char(ch: str, rng: np.random.Generator, rate: float) -> str:
    """Maybe replace *ch* with a confusable character."""
    if rng.random() < rate and ch in _CONFUSION_MAP:
        return _CONFUSION_MAP[ch]
    return ch


def _corrupt_text(text: str, rng: np.random.Generator, is_label: bool) -> str:
    """Apply character-level confusion to *text*."""
    rate = 0.005 if is_label else 0.015
    return "".join(_confuse_char(c, rng, rate) for c in text)


# ---------------------------------------------------------------------------
# Sub-bbox computation for word tokens within a line box
# ---------------------------------------------------------------------------

def _split_into_word_tokens(
    box: dict, rng: np.random.Generator
) -> list[dict]:
    """Split a ground-truth box into word-level sub-boxes.

    Sub-bboxes are computed proportionally based on character counts.
    """
    text = box["text"].strip()
    if not text:
        return []

    words = text.split()
    if not words:
        return []

    x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
    total_chars = sum(len(w) for w in words)
    total_width = x2 - x1

    # Small gap between words (proportional to a space character)
    n_gaps = len(words) - 1
    # Estimate space width as roughly 0.5 char width
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


# ---------------------------------------------------------------------------
# Sort helper
# ---------------------------------------------------------------------------

def _sort_key(tok: dict) -> tuple:
    """Top-to-bottom then left-to-right sort key."""
    # Use centre-y for primary sort, centre-x for secondary
    cy = (tok["y1"] + tok["y2"]) / 2
    cx = (tok["x1"] + tok["x2"]) / 2
    return (cy, cx)


# ---------------------------------------------------------------------------
# Line-grouping helper
# ---------------------------------------------------------------------------

def _assign_line_ids(tokens: list[dict]) -> list[dict]:
    """Group tokens into lines by y-proximity and assign sequential line_id.

    Tokens on the same visual line share a line_id.  A new line starts when
    the centre-y gap exceeds half the average token height.
    """
    if not tokens:
        return tokens

    # Compute average token height
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


# ---------------------------------------------------------------------------
# Main noise function
# ---------------------------------------------------------------------------

def apply_ocr_noise(
    boxes: list[dict],
    rng: np.random.Generator,
) -> list[dict]:
    """Apply the full OCR corruption pipeline and return OCR token dicts."""

    # ------------------------------------------------------------------ #
    # Step 1: split boxes into word tokens
    # ------------------------------------------------------------------ #
    raw_tokens: list[dict] = []
    for box in boxes:
        raw_tokens.extend(_split_into_word_tokens(box, rng))

    if not raw_tokens:
        return []

    # ------------------------------------------------------------------ #
    # Step 2: sort top-to-bottom then left-to-right
    # ------------------------------------------------------------------ #
    raw_tokens.sort(key=_sort_key)

    # ------------------------------------------------------------------ #
    # Step 3: assign line_id
    # ------------------------------------------------------------------ #
    raw_tokens = _assign_line_ids(raw_tokens)

    # ------------------------------------------------------------------ #
    # Step 4: bbox jitter ±2 px per coordinate
    # ------------------------------------------------------------------ #
    for tok in raw_tokens:
        for coord in ("x1", "y1", "x2", "y2"):
            jitter = int(rng.integers(-2, 3))  # -2, -1, 0, 1, 2
            tok[coord] = max(0, tok[coord] + jitter)

    # ------------------------------------------------------------------ #
    # Step 5: character confusion
    # ------------------------------------------------------------------ #
    for tok in raw_tokens:
        tok["text"] = _corrupt_text(tok["text"], rng, tok["is_label"])

    # ------------------------------------------------------------------ #
    # Step 6: token drop (1%)
    # ------------------------------------------------------------------ #
    kept: list[dict] = []
    for tok in raw_tokens:
        if rng.random() < 0.01:
            continue  # drop
        kept.append(tok)
    raw_tokens = kept

    # ------------------------------------------------------------------ #
    # Step 7: token merge (4% of adjacent same-line pairs)
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Step 8: token split (3% of tokens longer than 6 chars)
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Step 9: random label-line capitalization (10% of label lines)
    # ------------------------------------------------------------------ #
    # Collect label line IDs
    label_line_ids = {tok["line_id"] for tok in raw_tokens if tok["is_label"]}
    # Randomly pick 10% of those lines to capitalize
    lines_to_cap = {
        lid for lid in label_line_ids if rng.random() < 0.10
    }
    for tok in raw_tokens:
        if tok["line_id"] in lines_to_cap:
            tok["text"] = tok["text"].upper()

    # ------------------------------------------------------------------ #
    # Step 10: final sort (top-to-bottom then left-to-right)
    # ------------------------------------------------------------------ #
    raw_tokens.sort(key=_sort_key)

    # ------------------------------------------------------------------ #
    # Step 11: build final OCR token list with conf and correct bbox format
    # ------------------------------------------------------------------ #
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

# Document Extraction Task

## Overview

Extract structured fields from synthetic English single-page documents. Each document is provided as a directory containing a rendered page image, precomputed OCR tokens, and document metadata.

## Directory Structure

Each document directory has this layout:

```
doc_000001/
  meta.json
  ocr.json
  pages/
    0.png
  target.json   # train and val only
```

## Supported Schemas

- `government_id`
- `proof_of_address`
- `payment_receipt`

The active schema for a document is declared in `meta.json` as `schema_name`.

## Input Files

### `meta.json`

```json
{
  "doc_id": "doc_000001",
  "schema_name": "payment_receipt",
  "num_pages": 1,
  "language": "en"
}
```

### `ocr.json`

```json
{
  "pages": [
    {
      "page_index": 0,
      "width": 1600,
      "height": 2200,
      "tokens": [
        {
          "text": "Payment",
          "bbox": [100, 120, 220, 155],
          "line_id": 0,
          "block_id": 0,
          "conf": 0.96
        }
      ]
    }
  ]
}
```

- `bbox` is `[x1, y1, x2, y2]` in pixels
- tokens are sorted top-to-bottom then left-to-right
- `conf` is in `[0.82, 0.99]`

### `pages/0.png`

- 1600 × 2200 pixels
- PNG, white background, clean render

## Output Contract

Return a JSON object with this shape:

```json
{
  "schema_name": "<constant>",
  "fields": {
    "field_name": "value or null"
  }
}
```

All field values are `string | null`. Every required field must be present.

### `government_id` fields

- `full_name`
- `date_of_birth` — `YYYY-MM-DD`
- `document_number` — uppercase
- `issue_date` — `YYYY-MM-DD`
- `expiry_date` — `YYYY-MM-DD`
- `issuing_country` — full English name

### `proof_of_address` fields

- `full_name`
- `address_line1`
- `city`
- `postal_code`
- `country`
- `statement_date` — `YYYY-MM-DD`
- `issuer_name`

The customer address block always appears as exactly three lines:

```
<address_line1>
<city>, <postal_code>
<country>
```

### `payment_receipt` fields

- `sender_name`
- `recipient_name`
- `amount` — decimal string, e.g. `248.50`
- `currency` — `USD`, `EUR`, or `GBP`
- `payment_date` — `YYYY-MM-DD`
- `reference_id`

## Solution Entry Point

Implement `predict` in `extract.py`:

```python
def predict(document_dir: str) -> dict:
    ...
```

The function receives the path to one document directory and returns the prediction dict.

## Evaluation

Run the public validator:

```bash
uv run python task/tools/public_validator.py <solution_dir>
```

Scoring per document:

```
field_acc  = mean(exact_match per field)
exact_doc  = 1 if all fields match else 0
doc_score  = 0.9 * field_acc + 0.1 * exact_doc
```

Final score is macro-averaged across the three schemas.

## Tools

- `task/tools/canonicalize.py` — shared normalization logic
- `task/tools/public_validator.py` — evaluate on val split
- `task/tools/visualize_ocr.py` — inspect OCR overlay

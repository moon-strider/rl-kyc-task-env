# Document Extraction Task

## Overview

The task is to extract structured fields from synthetic single-page English-language documents. Each document is represented as a directory containing a page image, precomputed OCR tokens, and metadata.

## Directory Structure

Each document directory looks like this:

```text
doc_000001/
  meta.json
  ocr.json
  pages/
    0.png
  target.json
```

`target.json` is present only in `train` and `val`.

## Supported Schemas

- `government_id`
- `proof_of_address`
- `payment_receipt`

The active schema is specified in `meta.json` as `schema_name`.

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
- tokens are ordered top-to-bottom, then left-to-right
- `conf` is in the range `[0.82, 0.99]`

### `pages/0.png`

- `1600 x 2200` pixels
- PNG
- white background
- clean render without heavy scan artifacts

## Output Contract

Your solution must return a JSON object of the following form:

```json
{
  "schema_name": "<constant>",
  "fields": {
    "field_name": "value or null"
  }
}
```

All field values must be `string | null`. All required fields must be present.

### Fields for `government_id`

- `full_name`
- `date_of_birth` — `YYYY-MM-DD`
- `document_number` — uppercase
- `issue_date` — `YYYY-MM-DD`
- `expiry_date` — `YYYY-MM-DD`
- `issuing_country` — full English country name

### Fields for `proof_of_address`

- `full_name`
- `address_line1`
- `city`
- `postal_code`
- `country`
- `statement_date` — `YYYY-MM-DD`
- `issuer_name`

The customer address block always has exactly three lines:

```text
<address_line1>
<city>, <postal_code>
<country>
```

### Fields for `payment_receipt`

- `sender_name`
- `recipient_name`
- `amount` — decimal string, for example `248.50`
- `currency` — `USD`, `EUR`, or `GBP`
- `payment_date` — `YYYY-MM-DD`
- `reference_id`

## Solution Entrypoint

Implement `predict` in `extract.py`:

```python
def predict(document_dir: str) -> dict:
    ...
```

The function receives the path to one document directory and returns a prediction dictionary.

## Evaluation

Run the public validator:

```bash
uv run python task/tools/public_validator.py <solution_dir>
```

Per-document score:

```text
field_acc = mean(exact_match per field)
exact_doc = 1 if all fields match else 0
doc_score = 0.9 * field_acc + 0.1 * exact_doc
```

Final score is macro-averaged over the three schemas.

## Tools

- `task/tools/canonicalize.py` — shared normalization logic
- `task/tools/public_validator.py` — evaluation on `val`
- `task/tools/visualize_ocr.py` — OCR overlay visualization

# Document Extraction Assessment Environment

This repository contains a local assessment environment for structured extraction from synthetic but realistic English single-page documents. Each document directory includes `meta.json`, `ocr.json`, and `pages/0.png`. A solution reads those files and returns a structured JSON object for the schema declared in `meta.json`.

The environment focuses on robust extraction from noisy OCR and document layout. It includes synthetic data generation, a participant-facing task bundle, hidden evaluation, shared canonicalization, and two reference baselines.

## Scope

The repository uses a fixed setup:

- English documents only
- Single-page documents only
- Known document type in `meta.json` as `schema_name`
- Precomputed OCR in `ocr.json`
- Clean rendered page image in `pages/0.png`
- CPU-only local execution
- No network access, external APIs, OpenRouter, or GPU usage

Supported schemas:

- `government_id`
- `proof_of_address`
- `payment_receipt`

All target fields are present in every generated document.

## Repository Layout

```text
doc_extract_env/
  task/
    README.md
    prompt.txt
    schemas/
      government_id.schema.json
      proof_of_address.schema.json
      payment_receipt.schema.json
    public_data/
      train/
      val/
    tools/
      canonicalize.py
      public_validator.py
      visualize_ocr.py

  generator/
    generate_public.py
    generate_hidden.py
    render.py
    template_specs_public.py
    template_specs_private.py
    field_sampling.py
    ocr_noise.py
    utils.py

  judge/
    run_judge.py
    judge_utils.py

  private/
    hidden_test/
    hidden_gold/
    seed_config.json

  baselines/
    null_baseline/
      extract.py
    heuristic_baseline/
      extract.py

  pyproject.toml
  uv.lock
  justfile
  README.md
```

The public task bundle is the `task/` directory. Hidden assets remain under `private/`, with hidden gold labels stored separately from hidden document directories.

## Data

### Public splits

- `train`: 360 documents
- `val`: 90 documents

Per schema:

- `government_id`: 120 train, 30 val
- `proof_of_address`: 120 train, 30 val
- `payment_receipt`: 120 train, 30 val

### Hidden split

- `hidden_test`: 108 documents

Per schema:

- `government_id`: 36
- `proof_of_address`: 36
- `payment_receipt`: 36

### Template inventory

Each schema uses 6 templates:

- 4 public templates
- 2 private templates

Totals:

- 12 public templates
- 6 private templates
- 18 templates overall

## Document Format

Each public document directory has this structure:

```text
doc_000123/
  meta.json
  ocr.json
  pages/
    0.png
```

Public train and validation documents also include:

```text
  target.json
```

Hidden test documents contain only `meta.json`, `ocr.json`, and `pages/0.png`. Their gold targets are stored privately under `private/hidden_gold/`.

### `meta.json`

`meta.json` contains exactly:

```json
{
  "doc_id": "doc_000123",
  "schema_name": "payment_receipt",
  "num_pages": 1,
  "language": "en"
}
```

### `ocr.json`

`ocr.json` has this structure:

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

OCR properties:

- `bbox` format is `[x1, y1, x2, y2]` in pixels
- tokens are sorted top-to-bottom and then left-to-right
- `line_id` is unique within the page
- `block_id` is unique within the page
- `conf` is sampled in `[0.82, 0.99]`

### `pages/0.png`

- fixed size `1600x2200`
- PNG format
- white background
- clean render without heavy scan artifacts

## Output Contract

Every prediction has this top-level shape:

```json
{
  "schema_name": "<constant>",
  "fields": {
    "...": "..."
  }
}
```

Common rules:

- top-level type is `object`
- `additionalProperties` is `false`
- required top-level keys are `schema_name` and `fields`
- every field inside `fields` is required
- every field value is `string | null`

### `government_id`

Fields:

- `full_name`
- `date_of_birth`
- `document_number`
- `issue_date`
- `expiry_date`
- `issuing_country`

Expected formats:

- dates use `YYYY-MM-DD`
- `document_number` is uppercase
- `issuing_country` is a full English country name

### `proof_of_address`

Fields:

- `full_name`
- `address_line1`
- `city`
- `postal_code`
- `country`
- `statement_date`
- `issuer_name`

The customer address block always uses exactly three lines:

1. `<address_line1>`
2. `<city>, <postal_code>`
3. `<country>`

There is no state, region, or second address line.

### `payment_receipt`

Fields:

- `sender_name`
- `recipient_name`
- `amount`
- `currency`
- `payment_date`
- `reference_id`

Expected formats:

- `amount` is a decimal string such as `248.50`
- `currency` is `USD`, `EUR`, or `GBP`
- `payment_date` uses `YYYY-MM-DD`

## Template Catalog

### `government_id`

Public templates:

1. `gid_passport_grid`
2. `gid_idcard_compact`
3. `gid_form_official`
4. `gid_card_horizontal`

Private templates:

5. `gid_dense_smallcaps`
6. `gid_minimal_two_column`

### `proof_of_address`

Public templates:

1. `poa_utility_bill`
2. `poa_telecom_invoice`
3. `poa_bank_statement`
4. `poa_insurance_notice`

Private templates:

5. `poa_energy_statement_center`
6. `poa_water_bill_split`

### `payment_receipt`

Public templates:

1. `pay_bank_transfer`
2. `pay_wallet_receipt`
3. `pay_paid_invoice`
4. `pay_checkout_receipt`

Private templates:

5. `pay_merchant_confirmation`
6. `pay_transaction_slip`

## Generation

The generator uses Faker locales:

- `en_US`
- `en_GB`
- `en_CA`

### `government_id`

- `full_name`: 2–3 words without titles
- `date_of_birth`: between `1960-01-01` and `2005-12-31`
- `issue_date`: not earlier than `date_of_birth + 18 years`
- `expiry_date`: `issue_date + 5 years` or `issue_date + 10 years`
- `document_number` matches one of:
  - `[A-Z]\d{7}`
  - `[A-Z]{2}\d{6}`
  - `\d{9}`
- `issuing_country` is one of:
  - `United States`
  - `United Kingdom`
  - `Canada`
  - `Australia`
  - `Singapore`
  - `Germany`

### `proof_of_address`

- `full_name`: 2–3 words
- `address_line1`, `city`, `postal_code`, and `country` stay locale-consistent
- `statement_date`: between `2025-01-01` and `2026-03-31`
- `issuer_name`: company or provider name
- distractors include provider address, account number, and due date

### `payment_receipt`

- `sender_name`: person name
- `recipient_name`: company or merchant name
- `amount`: from `5.00` to `5000.00`
- `currency`: `USD`, `EUR`, or `GBP`
- `payment_date`: between `2025-01-01` and `2026-03-31`
- `reference_id` matches one of:
  - `TRX-\d{6}`
  - `PMT-\d{8}`
  - `REF[A-Z0-9]{7}`
- distractors include fee, tax, subtotal, invoice id, and authorization code

## OCR Characteristics

The OCR pipeline is fixed:

1. render a clean PNG document
2. record ground-truth text boxes during rendering
3. split rendered lines into tokens
4. apply OCR-like corruption
5. write corrupted tokens to `ocr.json`
6. keep `pages/0.png` clean

Noise parameters:

- bbox jitter: `±2 px` per coordinate
- char confusion: `1.5%` for value tokens and `0.5%` for label tokens
- substitutions: `O ↔ 0`, `I ↔ 1`, `l ↔ 1`, `S ↔ 5`, `B ↔ 8`
- token drop: `1%`
- token merge: `4%` of adjacent same-line pairs
- token split: `3%` of tokens longer than 6 characters
- random label capitalization: `10%` of label lines
- token confidence sampled uniformly in `[0.82, 0.99]`

## Label Synonyms

### `government_id`

- `full_name`: `Name`, `Full Name`, `Holder Name`, `Surname and Given Names`
- `date_of_birth`: `Date of Birth`, `DOB`, `Birth Date`
- `document_number`: `Document No.`, `Passport No.`, `ID Number`, `Doc No.`
- `issue_date`: `Issue Date`, `Date of Issue`, `Issued On`
- `expiry_date`: `Expiry Date`, `Date of Expiry`, `Valid Until`
- `issuing_country`: `Issuing Country`, `Country of Issue`, `Issued In`

### `proof_of_address`

Address block anchors:

- `Bill To`
- `Customer Name`
- `Account Holder`
- `Service Address`
- `Mailing Address`
- `Address`

Date labels:

- `Statement Date`
- `Bill Date`
- `Issued On`

`issuer_name` is the first line of the header block.

### `payment_receipt`

- `sender_name`: `From`, `Sender`, `Paid By`, `Payer`
- `recipient_name`: `To`, `Recipient`, `Merchant`, `Payee`
- `amount`: `Amount`, `Total Paid`, `Payment Amount`, `Total`
- `payment_date`: `Payment Date`, `Date`, `Processed On`
- `reference_id`: `Reference`, `Transaction ID`, `Payment Ref`, `Ref ID`

## Canonicalization

`task/tools/canonicalize.py` provides the shared public normalization logic used by validation and scoring.

General normalization:

- `unicodedata.normalize("NFKC", s)`
- trim whitespace
- collapse repeated spaces
- strip leading and trailing punctuation while preserving internal `-` and `/`
- compare ordinary text fields case-insensitively

Date parsing accepts:

- `YYYY-MM-DD`
- `DD Mon YYYY`
- `DD Month YYYY`
- `Mon DD, YYYY`
- `Month DD, YYYY`

Dates are normalized to `YYYY-MM-DD`.

Amount parsing accepts values like:

- `248.50`
- `248`
- `USD 248.50`
- `$248.50`
- `248.50 USD`

Amounts are normalized to exactly two fractional digits.

Currency normalization maps:

- `$`, `USD`, `US Dollar` → `USD`
- `€`, `EUR`, `Euro` → `EUR`
- `£`, `GBP`, `Pound Sterling` → `GBP`

Identifiers for `document_number` and `reference_id` use NFKC, uppercase, collapsed spaces, and preserved hyphens.

Postal codes use uppercase, collapsed spaces, and preserved hyphens.

## Baselines

### `null_baseline`

The null baseline returns the correct `schema_name` and `null` for every field.

### `heuristic_baseline`

The heuristic baseline reads `meta.json` and `ocr.json`, reconstructs lines from OCR, performs fuzzy label matching for `government_id` and `payment_receipt`, uses dedicated address-block logic for `proof_of_address`, and canonicalizes fields before returning.

## Evaluation

`task/tools/public_validator.py` evaluates solutions on `task/public_data/val`.

`judge/run_judge.py` evaluates solutions on `private/hidden_test` and loads hidden gold from `private/hidden_gold`.

Both evaluators:

- require `extract.py` in the provided solution directory
- run one Python subprocess per document
- call `predict(document_dir)`
- enforce a 5-second timeout per document
- assign `0.0` on import failure, exception, timeout, invalid structure, failed serialization, or schema validation failure
- canonicalize prediction and gold before comparison
- use identical scoring logic

Output format:

```json
{
  "score": 0.8123,
  "by_schema": {
    "government_id": 0.8450,
    "proof_of_address": 0.7817,
    "payment_receipt": 0.8102
  },
  "num_docs": 108
}
```

Judge output contains only aggregate metrics.

## Scoring

For one document:

- `field_acc = mean(exact_match(field_i))`
- `exact_doc = 1` if every field matches, otherwise `0`
- `doc_score = 0.9 * field_acc + 0.1 * exact_doc`

For one schema:

- `schema_score = mean(doc_score)` over that schema’s documents

Final score:

```text
(government_id_score + proof_of_address_score + payment_receipt_score) / 3
```

The final score is macro-averaged across the three schema families.

## Reproducibility

Fixed seeds:

- `PUBLIC_SEED = 20260413`
- `HIDDEN_SEED = 90731157`

`generator/generate_public.py` uses only `PUBLIC_SEED`.
`generator/generate_hidden.py` uses only `HIDDEN_SEED`.

## Runtime and Tooling

- Python 3.11 target runtime
- `uv` for environment and dependency management
- `just` for common repository commands
- Declared Python dependencies:
  - numpy
  - pandas
  - Pillow
  - rapidfuzz
  - python-dateutil
  - jsonschema
  - pydantic
  - Faker

## Typical Commands

```bash
uv sync
just generate-public
just generate-hidden
just validate-null
just validate-heuristic
just judge-null
just judge-heuristic
```

Direct command equivalents remain available when needed:

```bash
uv run python generator/generate_public.py
uv run python generator/generate_hidden.py
uv run python task/tools/public_validator.py baselines/null_baseline
uv run python task/tools/public_validator.py baselines/heuristic_baseline
uv run python judge/run_judge.py baselines/null_baseline
uv run python judge/run_judge.py baselines/heuristic_baseline
```

## Why This Design

The environment combines document layout, OCR noise, distractor fields, normalization, and hidden templates while remaining lightweight enough for local CPU-only execution. It models a realistic KYC and payment extraction task without turning into an OCR training, multilingual parsing, or infrastructure-heavy project.

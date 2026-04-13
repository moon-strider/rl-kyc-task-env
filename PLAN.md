# PLAN

## 1. Repository scaffold and dependencies
- [ ] Create the top-level repository structure:
  - [ ] `task/`
  - [ ] `generator/`
  - [ ] `judge/`
  - [ ] `private/`
  - [ ] `baselines/`
- [ ] Add the required top-level files:
  - [ ] `README.md`
  - [ ] `requirements.txt`
- [ ] Set the runtime target to Python 3.11.
- [ ] Add only the approved dependencies:
  - [ ] `numpy`
  - [ ] `pandas`
  - [ ] `Pillow`
  - [ ] `rapidfuzz`
  - [ ] `python-dateutil`
  - [ ] `jsonschema`
  - [ ] `pydantic`
  - [ ] `Faker`

## 2. Participant-facing task package
- [ ] Create `task/README.md` with the participant-facing task description.
- [ ] Create `task/prompt.txt` with the exact solution contract.
- [ ] State the required solution entry point exactly:
  - [ ] `def predict(document_dir: str) -> dict:`
- [ ] Ensure the task prompt points the evaluator to `/workspace/solution/extract.py`.
- [ ] Create `task/schemas/`.

## 3. Schema files
- [ ] Create `task/schemas/government_id.schema.json`.
- [ ] Define `government_id` fields exactly:
  - [ ] `full_name`
  - [ ] `date_of_birth`
  - [ ] `document_number`
  - [ ] `issue_date`
  - [ ] `expiry_date`
  - [ ] `issuing_country`
- [ ] Create `task/schemas/proof_of_address.schema.json`.
- [ ] Define `proof_of_address` fields exactly:
  - [ ] `full_name`
  - [ ] `address_line1`
  - [ ] `city`
  - [ ] `postal_code`
  - [ ] `country`
  - [ ] `statement_date`
  - [ ] `issuer_name`
- [ ] Create `task/schemas/payment_receipt.schema.json`.
- [ ] Define `payment_receipt` fields exactly:
  - [ ] `sender_name`
  - [ ] `recipient_name`
  - [ ] `amount`
  - [ ] `currency`
  - [ ] `payment_date`
  - [ ] `reference_id`
- [ ] For all three schemas:
  - [ ] Set top-level type to `object`.
  - [ ] Require `schema_name` and `fields`.
  - [ ] Set `additionalProperties` to `false`.
  - [ ] Require every field inside `fields`.
  - [ ] Allow every field value to be `string | null`.

## 4. Public task data and tools directories
- [ ] Create `task/public_data/train/`.
- [ ] Create `task/public_data/val/`.
- [ ] Create `task/tools/`.
- [ ] Add:
  - [ ] `task/tools/canonicalize.py`
  - [ ] `task/tools/public_validator.py`
  - [ ] `task/tools/visualize_ocr.py`

## 5. Shared canonicalization logic
- [ ] Implement NFKC normalization for text values.
- [ ] Trim leading and trailing whitespace.
- [ ] Collapse repeated internal spaces.
- [ ] Strip leading and trailing punctuation while preserving internal `-` and `/`.
- [ ] Compare ordinary text fields case-insensitively.
- [ ] Implement date parsing for:
  - [ ] `YYYY-MM-DD`
  - [ ] `DD Mon YYYY`
  - [ ] `DD Month YYYY`
  - [ ] `Mon DD, YYYY`
  - [ ] `Month DD, YYYY`
- [ ] Normalize parsed dates to `YYYY-MM-DD`.
- [ ] Implement amount normalization for inputs such as:
  - [ ] `248.50`
  - [ ] `248`
  - [ ] `USD 248.50`
  - [ ] `$248.50`
  - [ ] `248.50 USD`
- [ ] Normalize amounts to a decimal string with exactly two fractional digits.
- [ ] Implement currency normalization mappings:
  - [ ] `$`, `USD`, `US Dollar` → `USD`
  - [ ] `€`, `EUR`, `Euro` → `EUR`
  - [ ] `£`, `GBP`, `Pound Sterling` → `GBP`
- [ ] Implement identifier normalization for `document_number` and `reference_id`:
  - [ ] NFKC normalize
  - [ ] Uppercase
  - [ ] Remove extra spaces
  - [ ] Preserve hyphens
- [ ] Implement postal code normalization:
  - [ ] Uppercase
  - [ ] Collapse spaces
  - [ ] Preserve hyphens
- [ ] Expose canonicalization in a form reusable by validator, judge, and baselines.

## 6. Scoring logic
- [ ] Implement canonicalized field-level exact match scoring.
- [ ] Implement per-document field accuracy:
  - [ ] `field_acc = mean(exact_match(field_i))`
- [ ] Implement exact-document bonus:
  - [ ] `exact_doc = 1` when every field matches, else `0`
- [ ] Implement document score:
  - [ ] `doc_score = 0.9 * field_acc + 0.1 * exact_doc`
- [ ] Implement per-schema mean score across documents.
- [ ] Implement final macro-average across:
  - [ ] `government_id`
  - [ ] `proof_of_address`
  - [ ] `payment_receipt`

## 7. Generator utilities
- [ ] Create `generator/utils.py`.
- [ ] Add helpers for:
  - [ ] deterministic seeding
  - [ ] split-aware output paths
  - [ ] document id creation
  - [ ] JSON serialization
  - [ ] directory creation
  - [ ] image and OCR artifact writing

## 8. Field sampling
- [ ] Create `generator/field_sampling.py`.
- [ ] Use only Faker locales:
  - [ ] `en_US`
  - [ ] `en_GB`
  - [ ] `en_CA`
- [ ] Implement `government_id` sampling rules:
  - [ ] `full_name` is 2–3 words with no titles
  - [ ] `date_of_birth` is between `1960-01-01` and `2005-12-31`
  - [ ] `issue_date` is not earlier than `date_of_birth + 18 years`
  - [ ] `expiry_date` is `issue_date + 5 years` or `issue_date + 10 years`
  - [ ] `document_number` matches one of:
    - [ ] `[A-Z]\d{7}`
    - [ ] `[A-Z]{2}\d{6}`
    - [ ] `\d{9}`
  - [ ] `issuing_country` is one of:
    - [ ] `United States`
    - [ ] `United Kingdom`
    - [ ] `Canada`
    - [ ] `Australia`
    - [ ] `Singapore`
    - [ ] `Germany`
- [ ] Implement `proof_of_address` sampling rules:
  - [ ] `full_name` is 2–3 words
  - [ ] `address_line1`, `city`, `postal_code`, and `country` stay locale-consistent
  - [ ] `statement_date` is between `2025-01-01` and `2026-03-31`
  - [ ] `issuer_name` is a company or provider name
  - [ ] distractors include:
    - [ ] provider address block
    - [ ] account number
    - [ ] due date in `statement_date + 10..21 days`
- [ ] Implement `payment_receipt` sampling rules:
  - [ ] `sender_name` is a person name
  - [ ] `recipient_name` is a company or merchant name
  - [ ] `amount` ranges from `5.00` to `5000.00`
  - [ ] `currency` is `USD`, `EUR`, or `GBP`
  - [ ] `payment_date` is between `2025-01-01` and `2026-03-31`
  - [ ] `reference_id` matches one of:
    - [ ] `TRX-\d{6}`
    - [ ] `PMT-\d{8}`
    - [ ] `REF[A-Z0-9]{7}`
  - [ ] distractors include:
    - [ ] fee
    - [ ] tax
    - [ ] subtotal
    - [ ] invoice id
    - [ ] authorization code
- [ ] Ensure every generated document contains all target fields.

## 9. Template catalog
- [ ] Create `generator/template_specs_public.py`.
- [ ] Create `generator/template_specs_private.py`.
- [ ] Define the public `government_id` templates exactly:
  - [ ] `gid_passport_grid`
  - [ ] `gid_idcard_compact`
  - [ ] `gid_form_official`
  - [ ] `gid_card_horizontal`
- [ ] Define the private `government_id` templates exactly:
  - [ ] `gid_dense_smallcaps`
  - [ ] `gid_minimal_two_column`
- [ ] Define the public `proof_of_address` templates exactly:
  - [ ] `poa_utility_bill`
  - [ ] `poa_telecom_invoice`
  - [ ] `poa_bank_statement`
  - [ ] `poa_insurance_notice`
- [ ] Define the private `proof_of_address` templates exactly:
  - [ ] `poa_energy_statement_center`
  - [ ] `poa_water_bill_split`
- [ ] Define the public `payment_receipt` templates exactly:
  - [ ] `pay_bank_transfer`
  - [ ] `pay_wallet_receipt`
  - [ ] `pay_paid_invoice`
  - [ ] `pay_checkout_receipt`
- [ ] Define the private `payment_receipt` templates exactly:
  - [ ] `pay_merchant_confirmation`
  - [ ] `pay_transaction_slip`
- [ ] Keep public and private template definitions separate.
- [ ] Ensure templates include realistic distractors matching the schema families.

## 10. Label vocabulary
- [ ] Encode `government_id` label variants:
  - [ ] `full_name`: `Name`, `Full Name`, `Holder Name`, `Surname and Given Names`
  - [ ] `date_of_birth`: `Date of Birth`, `DOB`, `Birth Date`
  - [ ] `document_number`: `Document No.`, `Passport No.`, `ID Number`, `Doc No.`
  - [ ] `issue_date`: `Issue Date`, `Date of Issue`, `Issued On`
  - [ ] `expiry_date`: `Expiry Date`, `Date of Expiry`, `Valid Until`
  - [ ] `issuing_country`: `Issuing Country`, `Country of Issue`, `Issued In`
- [ ] Encode `proof_of_address` address block anchors:
  - [ ] `Bill To`
  - [ ] `Customer Name`
  - [ ] `Account Holder`
  - [ ] `Service Address`
  - [ ] `Mailing Address`
  - [ ] `Address`
- [ ] Encode `proof_of_address` date labels:
  - [ ] `Statement Date`
  - [ ] `Bill Date`
  - [ ] `Issued On`
- [ ] Encode `payment_receipt` label variants:
  - [ ] `sender_name`: `From`, `Sender`, `Paid By`, `Payer`
  - [ ] `recipient_name`: `To`, `Recipient`, `Merchant`, `Payee`
  - [ ] `amount`: `Amount`, `Total Paid`, `Payment Amount`, `Total`
  - [ ] `payment_date`: `Payment Date`, `Date`, `Processed On`
  - [ ] `reference_id`: `Reference`, `Transaction ID`, `Payment Ref`, `Ref ID`

## 11. Rendering engine
- [ ] Create `generator/render.py`.
- [ ] Render a clean PNG page for every document.
- [ ] Fix page size at `1600x2200`.
- [ ] Use a white background.
- [ ] Keep the page image clean and free of heavy scan artifacts.
- [ ] Capture ground-truth text boxes during rendering.
- [ ] Support layout patterns required by all public and private templates.

## 12. OCR corruption pipeline
- [ ] Create `generator/ocr_noise.py`.
- [ ] Split rendered lines into tokens.
- [ ] Preserve token order top-to-bottom then left-to-right.
- [ ] Apply bbox jitter of `±2 px` on each coordinate.
- [ ] Apply char confusion rates:
  - [ ] `1.5%` for value tokens
  - [ ] `0.5%` for label tokens
- [ ] Restrict substitutions to:
  - [ ] `O ↔ 0`
  - [ ] `I ↔ 1`
  - [ ] `l ↔ 1`
  - [ ] `S ↔ 5`
  - [ ] `B ↔ 8`
- [ ] Apply token drop at `1%`.
- [ ] Apply token merge to `4%` of adjacent same-line pairs.
- [ ] Apply token split to `3%` of tokens longer than 6 characters.
- [ ] Apply random label capitalization to `10%` of label lines.
- [ ] Sample token confidence uniformly in `[0.82, 0.99]`.
- [ ] Keep `pages/0.png` clean while storing corrupted OCR in `ocr.json`.

## 13. Document serialization
- [ ] Write each document as:
  - [ ] `doc_<id>/meta.json`
  - [ ] `doc_<id>/ocr.json`
  - [ ] `doc_<id>/pages/0.png`
- [ ] Add `target.json` only to public train and validation documents.
- [ ] Write `meta.json` with exactly:
  - [ ] `doc_id`
  - [ ] `schema_name`
  - [ ] `num_pages`
  - [ ] `language`
- [ ] Ensure `num_pages = 1`.
- [ ] Ensure `language = "en"`.
- [ ] Write `ocr.json` with the exact page/token structure:
  - [ ] `pages`
  - [ ] `page_index`
  - [ ] `width`
  - [ ] `height`
  - [ ] `tokens`
  - [ ] `text`
  - [ ] `bbox`
  - [ ] `line_id`
  - [ ] `block_id`
  - [ ] `conf`

## 14. Public dataset generation
- [ ] Create `generator/generate_public.py`.
- [ ] Use only `PUBLIC_SEED = 20260413`.
- [ ] Generate exactly `360` public train documents.
- [ ] Generate exactly `90` public validation documents.
- [ ] Generate exactly `120` train and `30` validation documents per schema.
- [ ] Write output into `task/public_data/train/` and `task/public_data/val/`.
- [ ] Ensure only public assets are included in the public task bundle.

## 15. Hidden dataset generation
- [ ] Create `generator/generate_hidden.py`.
- [ ] Use only `HIDDEN_SEED = 90731157`.
- [ ] Generate exactly `108` hidden test documents.
- [ ] Generate exactly `36` hidden documents per schema.
- [ ] Store hidden outputs under `private/hidden_test/`.
- [ ] Create `private/seed_config.json`.
- [ ] Keep hidden assets outside the public task bundle.

## 16. OCR visualization utility
- [ ] Implement `task/tools/visualize_ocr.py`.
- [ ] Load `ocr.json` and `pages/0.png`.
- [ ] Overlay OCR boxes and token text for inspection.
- [ ] Make it usable for debugging token ordering, bbox quality, and corruption behavior.

## 17. Public validator
- [ ] Implement `task/tools/public_validator.py`.
- [ ] Accept a solution directory argument.
- [ ] Verify `extract.py` exists in the provided solution directory.
- [ ] Run one isolated Python subprocess per validation document.
- [ ] Import `predict` and call `predict(document_dir)`.
- [ ] Enforce a `5` second timeout per document.
- [ ] Assign `0.0` on:
  - [ ] import failure
  - [ ] exception
  - [ ] timeout
  - [ ] non-serializable output
  - [ ] malformed output
  - [ ] JSON Schema validation failure
- [ ] Canonicalize both prediction and gold output before comparison.
- [ ] Use the shared scoring logic.
- [ ] Output aggregate JSON results.

## 18. Judge internals
- [ ] Create `judge/judge_utils.py`.
- [ ] Put reusable evaluation helpers there for:
  - [ ] subprocess execution
  - [ ] timeout handling
  - [ ] serialization checks
  - [ ] schema validation
  - [ ] canonicalization
  - [ ] scoring
  - [ ] aggregation
- [ ] Keep judge logic aligned with public validator logic.

## 19. Hidden judge CLI
- [ ] Create `judge/run_judge.py`.
- [ ] Accept a solution directory argument.
- [ ] Verify `extract.py` exists in the provided solution directory.
- [ ] Evaluate against `private/hidden_test/`.
- [ ] Run one isolated subprocess per document.
- [ ] Import and call `predict(document_dir)` with a `5` second timeout.
- [ ] Apply the same failure handling as the public validator.
- [ ] Canonicalize prediction and gold output before scoring.
- [ ] Output only aggregate metrics:
  - [ ] `score`
  - [ ] `by_schema`
  - [ ] `num_docs`
- [ ] Do not expose per-document gold details.

## 20. Null baseline
- [ ] Create `baselines/null_baseline/extract.py`.
- [ ] Read `meta.json`.
- [ ] Return the correct `schema_name`.
- [ ] Return `null` for every required field in that schema.
- [ ] Ensure the output is JSON-serializable and schema-valid.

## 21. Heuristic baseline
- [ ] Create `baselines/heuristic_baseline/extract.py`.
- [ ] Read `meta.json` and `ocr.json`.
- [ ] Reconstruct lines from OCR tokens using `line_id`.
- [ ] Preserve line and block relationships needed for fallback extraction.
- [ ] For `government_id` and `payment_receipt`:
  - [ ] perform fuzzy label matching with `rapidfuzz`
  - [ ] extract the value to the right of the label on the same line
  - [ ] fall back to the nearest lower line in the same `block_id` when needed
- [ ] For `proof_of_address`:
  - [ ] locate the customer address block using the anchor labels
  - [ ] use the following line as `full_name`
  - [ ] parse the next three lines as:
    - [ ] `address_line1`
    - [ ] `city, postal_code`
    - [ ] `country`
  - [ ] extract `issuer_name` from the first line of the header block
  - [ ] search `statement_date` independently through the label variants
- [ ] Canonicalize all extracted fields before returning the prediction.

## 22. Root documentation
- [ ] Write the root `README.md` in present tense as a description of the existing system.
- [ ] Cover:
  - [ ] overview
  - [ ] scope
  - [ ] repository layout
  - [ ] task bundle
  - [ ] document format
  - [ ] schema contract
  - [ ] template catalog
  - [ ] generation and OCR behavior
  - [ ] canonicalization
  - [ ] baselines
  - [ ] validator and judge
  - [ ] scoring
  - [ ] reproducibility
  - [ ] requirements
  - [ ] commands
  - [ ] out-of-scope items
- [ ] Avoid roadmap, draft, or future-plan language.

## 23. Agent guidance document
- [ ] Write `AGENTS.md` as timeless project-specific operating instructions.
- [ ] Cover:
  - [ ] project identity
  - [ ] fixed scope
  - [ ] repository contract
  - [ ] schema and field rules
  - [ ] generation rules
  - [ ] reproducibility rules
  - [ ] validator and judge rules
  - [ ] baseline rules
  - [ ] dependency rules
  - [ ] implementation discipline
- [ ] Keep it instruction-focused.
- [ ] Avoid version labels, draft language, and roadmap language.

## 24. Public bundle integrity
- [ ] Confirm the public task bundle contains only:
  - [ ] `task/README.md`
  - [ ] `task/prompt.txt`
  - [ ] `task/schemas/`
  - [ ] `task/public_data/train/`
  - [ ] `task/public_data/val/`
  - [ ] `task/tools/canonicalize.py`
  - [ ] `task/tools/public_validator.py`
  - [ ] `task/tools/visualize_ocr.py`
- [ ] Confirm `private/` is excluded from the public task bundle.

## 25. End-to-end verification
- [ ] Create a clean virtual environment.
- [ ] Install `requirements.txt`.
- [ ] Run `python generator/generate_public.py`.
- [ ] Confirm public counts:
  - [ ] train = `360`
  - [ ] val = `90`
  - [ ] `government_id`: `120` train / `30` val
  - [ ] `proof_of_address`: `120` train / `30` val
  - [ ] `payment_receipt`: `120` train / `30` val
- [ ] Run `python generator/generate_hidden.py`.
- [ ] Confirm hidden counts:
  - [ ] total = `108`
  - [ ] `government_id`: `36`
  - [ ] `proof_of_address`: `36`
  - [ ] `payment_receipt`: `36`
- [ ] Confirm all public documents pass schema and format checks.
- [ ] Run `python task/tools/public_validator.py baselines/null_baseline`.
- [ ] Confirm the public null baseline score is not above `0.10`.
- [ ] Run `python task/tools/public_validator.py baselines/heuristic_baseline`.
- [ ] Confirm the public heuristic baseline total score is at least `0.80`.
- [ ] Run `python judge/run_judge.py baselines/null_baseline`.
- [ ] Confirm the hidden null baseline score is not above `0.10`.
- [ ] Run `python judge/run_judge.py baselines/heuristic_baseline`.
- [ ] Confirm the hidden heuristic baseline score is:
  - [ ] at least `0.65`
  - [ ] not above `0.90`

## 26. Final scope and contract audit
- [ ] Confirm the environment remains English-only.
- [ ] Confirm the environment remains single-page only.
- [ ] Confirm no real OCR engine is required.
- [ ] Confirm no handwriting support is introduced.
- [ ] Confirm no face matching or liveness features are introduced.
- [ ] Confirm no tampering detection is introduced.
- [ ] Confirm no PDF parsing workflow is introduced.
- [ ] Confirm no external APIs are required.
- [ ] Confirm no GPU requirement is introduced.
- [ ] Confirm all file names, schema names, field names, output formats, and template names match the contract exactly.
- [ ] Confirm hidden assets remain private.
- [ ] Confirm generation is reproducible from the fixed seeds.

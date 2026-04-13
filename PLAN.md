# PLAN

## 1. Repository scaffold and dependencies
- [x] Create the top-level repository structure:
  - [x] `task/`
  - [x] `generator/`
  - [x] `judge/`
  - [x] `private/`
  - [x] `baselines/`
- [x] Add the required top-level files:
  - [x] `README.md`
  - [x] `pyproject.toml`
  - [x] `uv.lock`
  - [x] `justfile`
- [x] Set the runtime target to Python 3.11.
- [x] Add only the approved dependencies in `pyproject.toml`:
  - [x] `numpy`
  - [x] `pandas`
  - [x] `Pillow`
  - [x] `rapidfuzz`
  - [x] `python-dateutil`
  - [x] `jsonschema`
  - [x] `pydantic`
  - [x] `Faker`
- [x] Add `justfile` recipes for the common generation and evaluation workflows.

## 2. Participant-facing task package
- [x] Create `task/README.md` with the participant-facing task description.
- [x] Create `task/prompt.txt` with the exact solution contract.
- [x] State the required solution entry point exactly:
  - [x] `def predict(document_dir: str) -> dict:`
- [x] Ensure the task prompt points the evaluator to `/workspace/solution/extract.py`.
- [x] Create `task/schemas/`.

## 3. Schema files
- [x] Create `task/schemas/government_id.schema.json`.
- [x] Define `government_id` fields exactly:
  - [x] `full_name`
  - [x] `date_of_birth`
  - [x] `document_number`
  - [x] `issue_date`
  - [x] `expiry_date`
  - [x] `issuing_country`
- [x] Create `task/schemas/proof_of_address.schema.json`.
- [x] Define `proof_of_address` fields exactly:
  - [x] `full_name`
  - [x] `address_line1`
  - [x] `city`
  - [x] `postal_code`
  - [x] `country`
  - [x] `statement_date`
  - [x] `issuer_name`
- [x] Create `task/schemas/payment_receipt.schema.json`.
- [x] Define `payment_receipt` fields exactly:
  - [x] `sender_name`
  - [x] `recipient_name`
  - [x] `amount`
  - [x] `currency`
  - [x] `payment_date`
  - [x] `reference_id`
- [x] For all three schemas:
  - [x] Set top-level type to `object`.
  - [x] Require `schema_name` and `fields`.
  - [x] Set `additionalProperties` to `false`.
  - [x] Require every field inside `fields`.
  - [x] Allow every field value to be `string | null`.

## 4. Public task data and tools directories
- [x] Create `task/public_data/train/`.
- [x] Create `task/public_data/val/`.
- [x] Create `task/tools/`.
- [x] Add:
  - [x] `task/tools/canonicalize.py`
  - [x] `task/tools/public_validator.py`
  - [x] `task/tools/visualize_ocr.py`

## 5. Shared canonicalization logic
- [x] Implement NFKC normalization for text values.
- [x] Trim leading and trailing whitespace.
- [x] Collapse repeated internal spaces.
- [x] Strip leading and trailing punctuation while preserving internal `-` and `/`.
- [x] Compare ordinary text fields case-insensitively.
- [x] Implement date parsing for:
  - [x] `YYYY-MM-DD`
  - [x] `DD Mon YYYY`
  - [x] `DD Month YYYY`
  - [x] `Mon DD, YYYY`
  - [x] `Month DD, YYYY`
- [x] Normalize parsed dates to `YYYY-MM-DD`.
- [x] Implement amount normalization for inputs such as:
  - [x] `248.50`
  - [x] `248`
  - [x] `USD 248.50`
  - [x] `$248.50`
  - [x] `248.50 USD`
- [x] Normalize amounts to a decimal string with exactly two fractional digits.
- [x] Implement currency normalization mappings:
  - [x] `$`, `USD`, `US Dollar` → `USD`
  - [x] `€`, `EUR`, `Euro` → `EUR`
  - [x] `£`, `GBP`, `Pound Sterling` → `GBP`
- [x] Implement identifier normalization for `document_number` and `reference_id`:
  - [x] NFKC normalize
  - [x] Uppercase
  - [x] Remove extra spaces
  - [x] Preserve hyphens
- [x] Implement postal code normalization:
  - [x] Uppercase
  - [x] Collapse spaces
  - [x] Preserve hyphens
- [x] Expose canonicalization in a form reusable by validator, judge, and baselines.

## 6. Scoring logic
- [x] Implement canonicalized field-level exact match scoring.
- [x] Implement per-document field accuracy:
  - [x] `field_acc = mean(exact_match(field_i))`
- [x] Implement exact-document bonus:
  - [x] `exact_doc = 1` when every field matches, else `0`
- [x] Implement document score:
  - [x] `doc_score = 0.9 * field_acc + 0.1 * exact_doc`
- [x] Implement per-schema mean score across documents.
- [x] Implement final macro-average across:
  - [x] `government_id`
  - [x] `proof_of_address`
  - [x] `payment_receipt`

## 7. Generator utilities
- [x] Create `generator/utils.py`.
- [x] Add helpers for:
  - [x] deterministic seeding
  - [x] split-aware output paths
  - [x] document id creation
  - [x] JSON serialization
  - [x] directory creation
  - [x] image and OCR artifact writing

## 8. Field sampling
- [x] Create `generator/field_sampling.py`.
- [x] Use only Faker locales:
  - [x] `en_US`
  - [x] `en_GB`
  - [x] `en_CA`
- [x] Implement `government_id` sampling rules:
  - [x] `full_name` is 2–3 words with no titles
  - [x] `date_of_birth` is between `1960-01-01` and `2005-12-31`
  - [x] `issue_date` is not earlier than `date_of_birth + 18 years`
  - [x] `expiry_date` is `issue_date + 5 years` or `issue_date + 10 years`
  - [x] `document_number` matches one of:
    - [x] `[A-Z]\d{7}`
    - [x] `[A-Z]{2}\d{6}`
    - [x] `\d{9}`
  - [x] `issuing_country` is one of:
    - [x] `United States`
    - [x] `United Kingdom`
    - [x] `Canada`
    - [x] `Australia`
    - [x] `Singapore`
    - [x] `Germany`
- [x] Implement `proof_of_address` sampling rules:
  - [x] `full_name` is 2–3 words
  - [x] `address_line1`, `city`, `postal_code`, and `country` stay locale-consistent
  - [x] `statement_date` is between `2025-01-01` and `2026-03-31`
  - [x] `issuer_name` is a company or provider name
  - [x] distractors include:
    - [x] provider address block
    - [x] account number
    - [x] due date in `statement_date + 10..21 days`
- [x] Implement `payment_receipt` sampling rules:
  - [x] `sender_name` is a person name
  - [x] `recipient_name` is a company or merchant name
  - [x] `amount` ranges from `5.00` to `5000.00`
  - [x] `currency` is `USD`, `EUR`, or `GBP`
  - [x] `payment_date` is between `2025-01-01` and `2026-03-31`
  - [x] `reference_id` matches one of:
    - [x] `TRX-\d{6}`
    - [x] `PMT-\d{8}`
    - [x] `REF[A-Z0-9]{7}`
  - [x] distractors include:
    - [x] fee
    - [x] tax
    - [x] subtotal
    - [x] invoice id
    - [x] authorization code
- [x] Ensure every generated document contains all target fields.

## 9. Template catalog
- [x] Create `generator/template_specs_public.py`.
- [x] Create `generator/template_specs_private.py`.
- [x] Define the public `government_id` templates exactly:
  - [x] `gid_passport_grid`
  - [x] `gid_idcard_compact`
  - [x] `gid_form_official`
  - [x] `gid_card_horizontal`
- [x] Define the private `government_id` templates exactly:
  - [x] `gid_dense_smallcaps`
  - [x] `gid_minimal_two_column`
- [x] Define the public `proof_of_address` templates exactly:
  - [x] `poa_utility_bill`
  - [x] `poa_telecom_invoice`
  - [x] `poa_bank_statement`
  - [x] `poa_insurance_notice`
- [x] Define the private `proof_of_address` templates exactly:
  - [x] `poa_energy_statement_center`
  - [x] `poa_water_bill_split`
- [x] Define the public `payment_receipt` templates exactly:
  - [x] `pay_bank_transfer`
  - [x] `pay_wallet_receipt`
  - [x] `pay_paid_invoice`
  - [x] `pay_checkout_receipt`
- [x] Define the private `payment_receipt` templates exactly:
  - [x] `pay_merchant_confirmation`
  - [x] `pay_transaction_slip`
- [x] Keep public and private template definitions separate.
- [x] Ensure templates include realistic distractors matching the schema families.

## 10. Label vocabulary
- [x] Encode `government_id` label variants:
  - [x] `full_name`: `Name`, `Full Name`, `Holder Name`, `Surname and Given Names`
  - [x] `date_of_birth`: `Date of Birth`, `DOB`, `Birth Date`
  - [x] `document_number`: `Document No.`, `Passport No.`, `ID Number`, `Doc No.`
  - [x] `issue_date`: `Issue Date`, `Date of Issue`, `Issued On`
  - [x] `expiry_date`: `Expiry Date`, `Date of Expiry`, `Valid Until`
  - [x] `issuing_country`: `Issuing Country`, `Country of Issue`, `Issued In`
- [x] Encode `proof_of_address` address block anchors:
  - [x] `Bill To`
  - [x] `Customer Name`
  - [x] `Account Holder`
  - [x] `Service Address`
  - [x] `Mailing Address`
  - [x] `Address`
- [x] Encode `proof_of_address` date labels:
  - [x] `Statement Date`
  - [x] `Bill Date`
  - [x] `Issued On`
- [x] Encode `payment_receipt` label variants:
  - [x] `sender_name`: `From`, `Sender`, `Paid By`, `Payer`
  - [x] `recipient_name`: `To`, `Recipient`, `Merchant`, `Payee`
  - [x] `amount`: `Amount`, `Total Paid`, `Payment Amount`, `Total`
  - [x] `payment_date`: `Payment Date`, `Date`, `Processed On`
  - [x] `reference_id`: `Reference`, `Transaction ID`, `Payment Ref`, `Ref ID`

## 11. Rendering engine
- [x] Create `generator/render.py`.
- [x] Render a clean PNG page for every document.
- [x] Fix page size at `1600x2200`.
- [x] Use a white background.
- [x] Keep the page image clean and free of heavy scan artifacts.
- [x] Capture ground-truth text boxes during rendering.
- [x] Support layout patterns required by all public and private templates.

## 12. OCR corruption pipeline
- [x] Create `generator/ocr_noise.py`.
- [x] Split rendered lines into tokens.
- [x] Preserve token order top-to-bottom then left-to-right.
- [x] Apply bbox jitter of `±2 px` on each coordinate.
- [x] Apply char confusion rates:
  - [x] `1.5%` for value tokens
  - [x] `0.5%` for label tokens
- [x] Restrict substitutions to:
  - [x] `O ↔ 0`
  - [x] `I ↔ 1`
  - [x] `l ↔ 1`
  - [x] `S ↔ 5`
  - [x] `B ↔ 8`
- [x] Apply token drop at `1%`.
- [x] Apply token merge to `4%` of adjacent same-line pairs.
- [x] Apply token split to `3%` of tokens longer than 6 characters.
- [x] Apply random label capitalization to `10%` of label lines.
- [x] Sample token confidence uniformly in `[0.82, 0.99]`.
- [x] Keep `pages/0.png` clean while storing corrupted OCR in `ocr.json`.

## 13. Document serialization
- [x] Write each document as:
  - [x] `doc_<id>/meta.json`
  - [x] `doc_<id>/ocr.json`
  - [x] `doc_<id>/pages/0.png`
- [x] Add `target.json` only to public train and validation documents.
- [x] Write `meta.json` with exactly:
  - [x] `doc_id`
  - [x] `schema_name`
  - [x] `num_pages`
  - [x] `language`
- [x] Ensure `num_pages = 1`.
- [x] Ensure `language = "en"`.
- [x] Write `ocr.json` with the exact page/token structure:
  - [x] `pages`
  - [x] `page_index`
  - [x] `width`
  - [x] `height`
  - [x] `tokens`
  - [x] `text`
  - [x] `bbox`
  - [x] `line_id`
  - [x] `block_id`
  - [x] `conf`

## 14. Public dataset generation
- [x] Create `generator/generate_public.py`.
- [x] Use only `PUBLIC_SEED = 20260413`.
- [x] Generate exactly `360` public train documents.
- [x] Generate exactly `90` public validation documents.
- [x] Generate exactly `120` train and `30` validation documents per schema.
- [x] Write output into `task/public_data/train/` and `task/public_data/val/`.
- [x] Ensure only public assets are included in the public task bundle.

## 15. Hidden dataset generation
- [x] Create `generator/generate_hidden.py`.
- [x] Use only `HIDDEN_SEED = 90731157`.
- [x] Generate exactly `108` hidden test documents.
- [x] Generate exactly `36` hidden documents per schema.
- [x] Store hidden outputs under `private/hidden_test/`.
- [x] Create `private/seed_config.json`.
- [x] Keep hidden assets outside the public task bundle.

## 16. OCR visualization utility
- [x] Implement `task/tools/visualize_ocr.py`.
- [x] Load `ocr.json` and `pages/0.png`.
- [x] Overlay OCR boxes and token text for inspection.
- [x] Make it usable for debugging token ordering, bbox quality, and corruption behavior.

## 17. Public validator
- [x] Implement `task/tools/public_validator.py`.
- [x] Accept a solution directory argument.
- [x] Verify `extract.py` exists in the provided solution directory.
- [x] Run one isolated Python subprocess per validation document.
- [x] Import `predict` and call `predict(document_dir)`.
- [x] Enforce a `5` second timeout per document.
- [x] Assign `0.0` on:
  - [x] import failure
  - [x] exception
  - [x] timeout
  - [x] non-serializable output
  - [x] malformed output
  - [x] JSON Schema validation failure
- [x] Canonicalize both prediction and gold output before comparison.
- [x] Use the shared scoring logic.
- [x] Output aggregate JSON results.

## 18. Judge internals
- [x] Create `judge/judge_utils.py`.
- [x] Put reusable evaluation helpers there for:
  - [x] subprocess execution
  - [x] timeout handling
  - [x] serialization checks
  - [x] schema validation
  - [x] canonicalization
  - [x] scoring
  - [x] aggregation
- [x] Keep judge logic aligned with public validator logic.

## 19. Hidden judge CLI
- [x] Create `judge/run_judge.py`.
- [x] Accept a solution directory argument.
- [x] Verify `extract.py` exists in the provided solution directory.
- [x] Evaluate against `private/hidden_test/`.
- [x] Run one isolated subprocess per document.
- [x] Import and call `predict(document_dir)` with a `5` second timeout.
- [x] Apply the same failure handling as the public validator.
- [x] Canonicalize prediction and gold output before scoring.
- [x] Output only aggregate metrics:
  - [x] `score`
  - [x] `by_schema`
  - [x] `num_docs`
- [x] Do not expose per-document gold details.

## 20. Null baseline
- [x] Create `baselines/null_baseline/extract.py`.
- [x] Read `meta.json`.
- [x] Return the correct `schema_name`.
- [x] Return `null` for every required field in that schema.
- [x] Ensure the output is JSON-serializable and schema-valid.

## 21. Heuristic baseline
- [x] Create `baselines/heuristic_baseline/extract.py`.
- [x] Read `meta.json` and `ocr.json`.
- [x] Reconstruct lines from OCR tokens using `line_id`.
- [x] Preserve line and block relationships needed for fallback extraction.
- [x] For `government_id` and `payment_receipt`:
  - [x] perform fuzzy label matching with `rapidfuzz`
  - [x] extract the value to the right of the label on the same line
  - [x] fall back to the nearest lower line in the same `block_id` when needed
- [x] For `proof_of_address`:
  - [x] locate the customer address block using the anchor labels
  - [x] use the following line as `full_name`
  - [x] parse the next three lines as:
    - [x] `address_line1`
    - [x] `city, postal_code`
    - [x] `country`
  - [x] extract `issuer_name` from the first line of the header block
  - [x] search `statement_date` independently through the label variants
- [x] Canonicalize all extracted fields before returning the prediction.

## 22. Root documentation
- [x] Write the root `README.md` in present tense as a description of the existing system.
- [x] Cover:
  - [x] overview
  - [x] scope
  - [x] repository layout
  - [x] task bundle
  - [x] document format
  - [x] schema contract
  - [x] template catalog
  - [x] generation and OCR behavior
  - [x] canonicalization
  - [x] baselines
  - [x] validator and judge
  - [x] scoring
  - [x] reproducibility
  - [x] requirements
  - [x] commands
  - [x] out-of-scope items
- [x] Avoid roadmap, draft, or future-plan language.

## 23. Agent guidance document
- [x] Write `AGENTS.md` as timeless project-specific operating instructions.
- [x] Cover:
  - [x] project identity
  - [x] fixed scope
  - [x] repository contract
  - [x] schema and field rules
  - [x] generation rules
  - [x] reproducibility rules
  - [x] validator and judge rules
  - [x] baseline rules
  - [x] dependency rules
  - [x] implementation discipline
- [x] Keep it instruction-focused.
- [x] Avoid version labels, draft language, and roadmap language.

## 24. Public bundle integrity
- [x] Confirm the public task bundle contains only:
  - [x] `task/README.md`
  - [x] `task/prompt.txt`
  - [x] `task/schemas/`
  - [x] `task/public_data/train/`
  - [x] `task/public_data/val/`
  - [x] `task/tools/canonicalize.py`
  - [x] `task/tools/public_validator.py`
  - [x] `task/tools/visualize_ocr.py`
- [x] Confirm `private/` is excluded from the public task bundle.

## 25. End-to-end verification
- [x] Run `uv sync`.
- [x] Run `just generate-public`.
- [x] Confirm public counts:
  - [x] train = `360`
  - [x] val = `90`
  - [x] `government_id`: `120` train / `30` val
  - [x] `proof_of_address`: `120` train / `30` val
  - [x] `payment_receipt`: `120` train / `30` val
- [x] Run `just generate-hidden`.
- [x] Confirm hidden counts:
  - [x] total = `108`
  - [x] `government_id`: `36`
  - [x] `proof_of_address`: `36`
  - [x] `payment_receipt`: `36`
- [x] Confirm all public documents pass schema and format checks.
- [x] Run `just validate-null`.
- [x] Confirm the public null baseline score is not above `0.10`.
- [x] Run `just validate-heuristic`.
- [x] Confirm the public heuristic baseline total score is at least `0.80`.
- [x] Run `just judge-null`.
- [x] Confirm the hidden null baseline score is not above `0.10`.
- [x] Run `just judge-heuristic`.
- [x] Confirm the hidden heuristic baseline score is:
  - [x] at least `0.65`
  - [x] not above `0.90`

## 26. Final scope and contract audit
- [x] Confirm the environment remains English-only.
- [x] Confirm the environment remains single-page only.
- [x] Confirm no real OCR engine is required.
- [x] Confirm no handwriting support is introduced.
- [x] Confirm no face matching or liveness features are introduced.
- [x] Confirm no tampering detection is introduced.
- [x] Confirm no PDF parsing workflow is introduced.
- [x] Confirm no external APIs are required.
- [x] Confirm no GPU requirement is introduced.
- [x] Confirm all file names, schema names, field names, output formats, and template names match the contract exactly.
- [ ] Define an external coding-agent evaluation harness that gives a model only the public task bundle and asks it to produce `/workspace/solution/extract.py`.
- [ ] Prepare a minimal Mistral coding-agent demo loop:
  - [ ] choose a Mistral model and runtime interface
  - [ ] assemble the model context from `task/README.md`, `task/prompt.txt`, schemas, and a controlled subset of public examples
  - [ ] save the generated answer as `extract.py` in an isolated solution directory
  - [ ] run `just validate-public <solution_dir>` and capture the aggregate score
  - [ ] feed back concise validator results for one or more repair iterations
  - [ ] run `just judge-hidden <solution_dir>` only after the public run is acceptable
- [x] Confirm the repository already contains the prerequisites for that demo:
  - [x] reproducible public data generation
  - [x] reproducible hidden data generation
  - [x] participant-facing task bundle
  - [x] public validator
  - [x] hidden judge
  - [x] baseline solutions for reference
  - [x] `uv` and `just` workflows for repeatable execution
- [ ] Define comparison criteria for external agent runs:
  - [ ] validity of generated `extract.py`
  - [ ] public validation score
  - [ ] hidden judge score
  - [ ] number of repair iterations needed
  - [ ] distance to the heuristic baseline

## 28. External RL training contour (deferred)
- [ ] Keep any RL loop outside this repository unless the project scope is explicitly expanded.
- [ ] If explored later, treat the current environment as an evaluator and reward source, not as the trainer itself (unless code hierarchy is changed to accomodate both RL pipeline and the environment).
- [ ] If explored later, define the contour around:
  - [ ] policy or model selection
  - [ ] rollout orchestration for code generation episodes
  - [ ] sandboxed execution of generated solutions
  - [ ] reward collection from the public validator
  - [ ] experiment tracking and checkpointing
- [ ] Preserve hidden data isolation if an external RL contour is added later.

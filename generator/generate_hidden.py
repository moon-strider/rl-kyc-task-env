"""Generate the hidden test dataset: 108 documents.

Uses only HIDDEN_SEED = 90731157.

Distribution:
  hidden_test: 36 government_id / 36 proof_of_address / 36 payment_receipt

Documents are interleaved by schema (index % 3 → schema).
All 6 templates (4 public + 2 private) are cycled per schema.

target.json is written alongside each document for judge scoring.

Run:
  python generator/generate_hidden.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from faker import Faker

from generator.utils import (
    HIDDEN_SEED,
    HIDDEN_TEST_DIR,
    doc_dir,
    format_doc_id,
    make_rng,
    write_meta,
    write_ocr,
    write_page_image,
    write_target,
)
from generator.field_sampling import (
    sample_government_id,
    sample_proof_of_address,
    sample_payment_receipt,
)
from generator.template_specs_public import PUBLIC_TEMPLATES, PUBLIC_TEMPLATE_NAMES
from generator.template_specs_private import PRIVATE_TEMPLATES, PRIVATE_TEMPLATE_NAMES
from generator.render import render_document
from generator.ocr_noise import apply_ocr_noise

# ---------------------------------------------------------------------------
# Schema ordering (interleaved)
# ---------------------------------------------------------------------------
_SCHEMAS = ["government_id", "proof_of_address", "payment_receipt"]
_DOCS_PER_SCHEMA = 36  # 36 per schema → 108 total

# Combined template lists per schema (public first, then private)
_ALL_TEMPLATE_NAMES: dict[str, list[str]] = {
    schema: PUBLIC_TEMPLATE_NAMES[schema] + PRIVATE_TEMPLATE_NAMES[schema]
    for schema in _SCHEMAS
}

_ALL_TEMPLATES = {**PUBLIC_TEMPLATES, **PRIVATE_TEMPLATES}


def _target_fields(schema_name: str, fields: dict) -> dict:
    if schema_name == "government_id":
        keys = ["full_name", "date_of_birth", "document_number",
                "issue_date", "expiry_date", "issuing_country"]
    elif schema_name == "proof_of_address":
        keys = ["full_name", "address_line1", "city", "postal_code",
                "country", "statement_date", "issuer_name"]
    else:  # payment_receipt
        keys = ["sender_name", "recipient_name", "amount", "currency",
                "payment_date", "reference_id"]
    return {k: fields[k] for k in keys}


def main() -> None:
    HIDDEN_TEST_DIR.mkdir(parents=True, exist_ok=True)

    master_rng = make_rng(HIDDEN_SEED)
    faker = Faker(["en_US", "en_GB", "en_CA"])
    faker.seed_instance(HIDDEN_SEED)

    total = _DOCS_PER_SCHEMA * len(_SCHEMAS)  # 108
    schema_counters: dict[str, int] = {s: 0 for s in _SCHEMAS}

    print(f"Generating hidden_test: {total} documents → {HIDDEN_TEST_DIR}")

    for doc_index in range(total):
        schema_name = _SCHEMAS[doc_index % 3]
        schema_idx = schema_counters[schema_name]
        schema_counters[schema_name] += 1

        # Template cycling (6 templates: 4 public + 2 private)
        template_names = _ALL_TEMPLATE_NAMES[schema_name]
        template_name = template_names[schema_idx % len(template_names)]
        template_fn = _ALL_TEMPLATES[template_name]

        # Per-document seed
        doc_seed = int(master_rng.integers(0, 2**31))
        doc_rng = np.random.default_rng(doc_seed)

        faker.seed_instance(doc_seed)

        # Sample fields
        if schema_name == "government_id":
            fields = sample_government_id(doc_rng, faker)
        elif schema_name == "proof_of_address":
            fields = sample_proof_of_address(doc_rng, faker, template_name)
        else:
            fields = sample_payment_receipt(doc_rng, faker)

        # Render
        elements = template_fn(fields)
        image, boxes = render_document(elements)

        # OCR noise
        ocr_tokens = apply_ocr_noise(boxes, doc_rng)

        # Write artifacts
        doc_id = format_doc_id(doc_index)
        dpath = doc_dir(HIDDEN_TEST_DIR, doc_id)

        write_meta(dpath, doc_id, schema_name)
        write_ocr(dpath, ocr_tokens)
        write_page_image(dpath, image)
        # target.json is written for judge scoring (private, not exposed to participants)
        write_target(dpath, schema_name, _target_fields(schema_name, fields))

        if (doc_index + 1) % 30 == 0 or doc_index == total - 1:
            print(f"  {doc_index + 1}/{total} done")

    print("Hidden generation complete.")
    print(f"  hidden_test → {HIDDEN_TEST_DIR}")


if __name__ == "__main__":
    main()

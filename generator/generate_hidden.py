                                                                       

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

                                 
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from faker import Faker

from generator.utils import (
    HIDDEN_GOLD_DIR,
    HIDDEN_SEED,
    HIDDEN_TEST_DIR,
    SEED_BANK_PATH,
    doc_dir,
    format_doc_id,
    make_rng,
    reset_output_dir,
    write_hidden_gold,
    write_meta,
    write_ocr,
    write_page_image,
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

                                                                             
                               
                                                                             
_SCHEMAS = ["government_id", "proof_of_address", "payment_receipt"]
_DOCS_PER_SCHEMA = 36                             

                                                                 
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
    else:                   
        keys = ["sender_name", "recipient_name", "amount", "currency",
                "payment_date", "reference_id"]
    return {k: fields[k] for k in keys}


def load_hidden_seed(seed: int | None, seed_name: str | None) -> int:
    if seed is not None and seed_name is not None:
        raise SystemExit("Use either --seed or --seed-name, not both")
    if seed is not None:
        return seed
    if seed_name is not None:
        seed_bank = json.loads(SEED_BANK_PATH.read_text(encoding="utf-8"))
        if seed_name not in seed_bank:
            known = ", ".join(sorted(seed_bank))
            raise SystemExit(f"Unknown seed name {seed_name!r}. Known seeds: {known}")
        return int(seed_bank[seed_name])
    return HIDDEN_SEED


def generate_hidden_dataset(hidden_test_dir: Path, hidden_gold_dir: Path, seed: int) -> None:
    reset_output_dir(hidden_test_dir)
    reset_output_dir(hidden_gold_dir)

    master_rng = make_rng(seed)
    faker = Faker(["en_US", "en_GB", "en_CA"])
    faker.seed_instance(seed)

    total = _DOCS_PER_SCHEMA * len(_SCHEMAS)       
    schema_counters: dict[str, int] = {s: 0 for s in _SCHEMAS}

    print(f"Generating hidden_test: {total} documents → {hidden_test_dir}")

    for doc_index in range(total):
        schema_name = _SCHEMAS[doc_index % 3]
        schema_idx = schema_counters[schema_name]
        schema_counters[schema_name] += 1

                                                              
        template_names = _ALL_TEMPLATE_NAMES[schema_name]
        template_name = template_names[schema_idx % len(template_names)]
        template_fn = _ALL_TEMPLATES[template_name]

                           
        doc_seed = int(master_rng.integers(0, 2**31))
        doc_rng = np.random.default_rng(doc_seed)

        faker.seed_instance(doc_seed)

                       
        if schema_name == "government_id":
            fields = sample_government_id(doc_rng, faker)
        elif schema_name == "proof_of_address":
            fields = sample_proof_of_address(doc_rng, faker, template_name)
        else:
            fields = sample_payment_receipt(doc_rng, faker)

                
        elements = template_fn(fields)
        image, boxes = render_document(elements)

                   
        ocr_tokens = apply_ocr_noise(boxes, doc_rng)

                         
        doc_id = format_doc_id(doc_index)
        dpath = doc_dir(hidden_test_dir, doc_id)

        write_meta(dpath, doc_id, schema_name)
        write_ocr(dpath, ocr_tokens)
        write_page_image(dpath, image)
        write_hidden_gold(hidden_gold_dir, doc_id, schema_name, _target_fields(schema_name, fields))

        if (doc_index + 1) % 30 == 0 or doc_index == total - 1:
            print(f"  {doc_index + 1}/{total} done")

    print("Hidden generation complete.")
    print(f"  hidden_test → {hidden_test_dir}")
    print(f"  hidden_gold → {hidden_gold_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--seed-name", default=None)
    parser.add_argument("--dataset-dir", default=str(HIDDEN_TEST_DIR))
    parser.add_argument("--gold-dir", default=str(HIDDEN_GOLD_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed = load_hidden_seed(args.seed, args.seed_name)
    generate_hidden_dataset(Path(args.dataset_dir), Path(args.gold_dir), seed)


if __name__ == "__main__":
    main()

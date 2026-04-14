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

import sys
from pathlib import Path

                                 
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from faker import Faker

from generator.utils import (
    PUBLIC_SEED,
    PUBLIC_TRAIN_DIR,
    PUBLIC_VAL_DIR,
    doc_dir,
    format_doc_id,
    make_rng,
    reset_output_dir,
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
from generator.render import render_document
from generator.ocr_noise import apply_ocr_noise

                                                                             
                               
                                                                             
_SCHEMAS = ["government_id", "proof_of_address", "payment_receipt"]

                                                         
_SPLITS = [
    ("train", PUBLIC_TRAIN_DIR, 120),
    ("val",   PUBLIC_VAL_DIR,   30),
]


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


def generate_split(
    split_name: str,
    output_dir: Path,
    docs_per_schema: int,
    master_rng: np.random.Generator,
    faker: Faker,
) -> None:
    total = docs_per_schema * len(_SCHEMAS)
                                                                            
    schema_counters: dict[str, int] = {s: 0 for s in _SCHEMAS}

    print(f"Generating {split_name}: {total} documents → {output_dir}")

    for doc_index in range(total):
        schema_name = _SCHEMAS[doc_index % 3]
        schema_idx = schema_counters[schema_name]
        schema_counters[schema_name] += 1

                                               
        template_names = PUBLIC_TEMPLATE_NAMES[schema_name]
        template_name = template_names[schema_idx % len(template_names)]
        template_fn = PUBLIC_TEMPLATES[template_name]

                                                   
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
        dpath = doc_dir(output_dir, doc_id)

        write_meta(dpath, doc_id, schema_name)
        write_ocr(dpath, ocr_tokens)
        write_page_image(dpath, image)
        write_target(dpath, schema_name, _target_fields(schema_name, fields))

        if (doc_index + 1) % 50 == 0 or doc_index == total - 1:
            print(f"  [{split_name}] {doc_index + 1}/{total} done")


def main() -> None:
    master_rng = make_rng(PUBLIC_SEED)
    faker = Faker(["en_US", "en_GB", "en_CA"])
    faker.seed_instance(PUBLIC_SEED)

    for split_name, output_dir, docs_per_schema in _SPLITS:
        reset_output_dir(output_dir)
        generate_split(split_name, output_dir, docs_per_schema, master_rng, faker)

    print("Public generation complete.")
    print(f"  train → {PUBLIC_TRAIN_DIR}")
    print(f"  val   → {PUBLIC_VAL_DIR}")


if __name__ == "__main__":
    main()

"""Fresh synthetic OCR comparison data with paired noise and separate gold.

This is an experiment dataset builder, not an untrusted-submission harness.
Generate dev first; generate holdout explicitly only after freezing prompt selection.
The held-out template families are already public in this repository's source.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Any

import numpy as np
from faker import Faker

from generator import field_sampling, ocr_noise, render, template_specs_private, template_specs_public, utils
from .schemas import SCHEMA_NAMES, field_names, load_schema, validate_prediction

SPLIT_SEEDS = {"dev": 2026091301, "holdout": 2026091302}
MISSING_FIELD = {
    "government_id": "document_number",
    "proof_of_address": "postal_code",
    "payment_receipt": "reference_id",
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _value_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def protocol() -> dict[str, Any]:
    """Return the full pre-generation protocol without sampling any documents."""
    sources = {"rl_kyc_task_env/comparison_dataset.py": _sha256(Path(__file__))}
    for module in [field_sampling, ocr_noise, render, template_specs_public,
                   template_specs_private, utils]:
        sources[f"generator/{Path(module.__file__).name}"] = _sha256(Path(module.__file__))
    families = {
        "dev": {schema: template_specs_public.PUBLIC_TEMPLATE_NAMES[schema][:3]
                for schema in SCHEMA_NAMES},
        "holdout": {schema: template_specs_private.PRIVATE_TEMPLATE_NAMES[schema][:2]
                    for schema in SCHEMA_NAMES},
    }
    for schema in SCHEMA_NAMES:
        if not set(families["dev"][schema]).isdisjoint(families["holdout"][schema]):
            raise ValueError("Dev and holdout template families must be disjoint")
        if len(families["dev"][schema]) != 3 or len(families["holdout"][schema]) != 2:
            raise ValueError("Expected three dev and two holdout families per schema")
    fonts = {}
    for name, location in [("regular", render._FONT_PATH_REGULAR), ("bold", render._FONT_PATH_BOLD)]:
        fonts[name] = ({"filename": Path(location).name, "sha256": _sha256(Path(location))}
                       if location else {"filename": "Pillow built-in", "sha256": None})
    return {
        "version": 1,
        "split_seeds": dict(SPLIT_SEEDS),
        "families": families,
        "families_visibility": "All template families are public in source; holdout means omitted from dev.",
        "dev": {"bases_per_family": 1, "ocr_profiles": ["standard_noise"], "documents": 9},
        "holdout": {"bases_per_family": 2, "ocr_profiles": ["clean", "standard_noise"],
                    "independent_base_documents": 12, "documents": 24},
        "missing_fields": {"base_index": 1, "by_schema": dict(MISSING_FIELD),
                           "rule": "Blank the value before template rendering; only its gold field becomes null."},
        "noise": "Existing apply_ocr_noise; each variant starts from the same clean rendered boxes.",
        "sources_sha256": sources,
        "schema_sha256": {schema: _value_sha256(load_schema(schema)) for schema in SCHEMA_NAMES},
        "versions": {name: importlib.metadata.version(name) for name in ["Faker", "numpy", "Pillow"]},
        "fonts": fonts,
    }


def sample_fields(schema: str, template: str, seed: int) -> dict[str, Any]:
    """Sample only through the existing deterministic synthetic constructors."""
    rng = np.random.default_rng(seed)
    faker = Faker(["en_US", "en_GB", "en_CA"])
    faker.seed_instance(seed)
    if schema == "government_id":
        return field_sampling.sample_government_id(rng, faker)
    if schema == "proof_of_address":
        return field_sampling.sample_proof_of_address(rng, faker, template)
    if schema == "payment_receipt":
        return field_sampling.sample_payment_receipt(rng, faker)
    raise ValueError(f"Unknown schema: {schema}")


def _tokens(boxes: list[dict], seed: int, profile: str) -> list[dict]:
    rng = np.random.default_rng(seed)
    if profile == "standard_noise":
        return ocr_noise.apply_ocr_noise(boxes, rng)
    raw = [token for box in boxes for token in ocr_noise._split_into_word_tokens(box, rng)]
    raw = ocr_noise._assign_line_ids(sorted(raw, key=ocr_noise._sort_key))
    return [{"text": token["text"], "bbox": [token[key] for key in ("x1", "y1", "x2", "y2")],
             "line_id": token["line_id"], "block_id": token["block_id"], "conf": 1.0}
            for token in raw]


def generate_split(output: Path, split: str, *, seed: int | None = None) -> dict[str, Any]:
    """Generate exactly one split under an exclusive external output directory.

    ``seed`` overrides are for independent reruns/tests. Neither this function nor
    ``protocol`` generates the other split, touches baseline data, or exports gold
    under the model-facing inputs directory.
    """
    if split not in SPLIT_SEEDS:
        raise ValueError("Split must be dev or holdout")
    seed = SPLIT_SEEDS[split] if seed is None else seed
    if type(seed) is not int or seed < 0:
        raise ValueError("Seed must be a nonnegative integer")
    spec = protocol()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    master = np.random.default_rng(seed)
    config = spec[split]
    builders = (template_specs_public.PUBLIC_TEMPLATES if split == "dev"
                else template_specs_private.PRIVATE_TEMPLATES)
    records = []
    for schema in SCHEMA_NAMES:
        for family_index, template in enumerate(spec["families"][split][schema]):
            for base_index in range(config["bases_per_family"]):
                doc_seed = int(master.integers(0, 2**31))
                ocr_seed = int(master.integers(0, 2**31))
                original = sample_fields(schema, template, doc_seed)
                fields = dict(original)
                missing = [MISSING_FIELD[schema]] if split == "holdout" and base_index == 1 else []
                for name in missing:
                    fields[name] = ""
                gold_fields = {name: None if name in missing else fields[name]
                               for name in field_names(schema)}
                gold = {"schema_name": schema, "fields": gold_fields}
                if not validate_prediction(schema, gold):
                    raise ValueError("Generated gold violates the public schema")
                elements = builders[template](fields)
                image, boxes = render.render_document(elements)
                image.close()
                base_id = f"{split}_{schema}_f{family_index:02d}_b{base_index:02d}"
                for profile in config["ocr_profiles"]:
                    doc_id = f"{base_id}_{profile}"
                    directory = output / "inputs" / doc_id
                    _write_json(directory / "meta.json", {
                        "doc_id": doc_id, "schema_name": schema, "num_pages": 1, "language": "en",
                    })
                    _write_json(directory / "ocr.json", {"pages": [{
                        "page_index": 0, "width": render.PAGE_W, "height": render.PAGE_H,
                        "tokens": _tokens(boxes, ocr_seed, profile),
                    }]})
                    gold_path = output / "gold" / f"{doc_id}.json"
                    _write_json(gold_path, gold)
                    records.append({
                        "doc_id": doc_id, "schema_name": schema, "base_id": base_id,
                        "base_index": base_index, "template": template, "seed": doc_seed,
                        "ocr_seed": ocr_seed, "ocr_profile": profile, "variant": profile,
                        "missing_fields": missing,
                        "original_fields_sha256": _value_sha256(original),
                        "rendered_fields_sha256": _value_sha256(fields),
                        "rendered_elements_sha256": _value_sha256(elements),
                        "ocr_sha256": _sha256(directory / "ocr.json"),
                        "gold_sha256": _sha256(gold_path),
                    })
    manifest = {
        "split": split, "seed": seed, "input_modality": "OCR only; no rendered pixels",
        "synthetic_only": True, "independent_base_documents": len({r["base_id"] for r in records}),
        "protocol": spec, "documents": records,
    }
    _write_json(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", required=True, choices=tuple(SPLIT_SEEDS))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    manifest = generate_split(args.output, args.split, seed=args.seed)
    print(json.dumps({"split": manifest["split"], "documents": len(manifest["documents"]),
                      "independent_base_documents": manifest["independent_base_documents"]}))


if __name__ == "__main__":
    main()

"""Run only AFTER comparison completion; validate evidence without editing it.

Use the RL project's Python environment. Reports JSON on stdout and exits nonzero
on failure. Keep redirected output outside the evidence directory, whose retained
file inventory is checked exactly. Regeneration writes only a temporary directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True
SEEDS = {"dev": 2026091301, "holdout": 2026091302}
SCHEMAS = ("government_id", "proof_of_address", "payment_receipt")
MISSING = {"government_id": "document_number", "proof_of_address": "postal_code",
           "payment_receipt": "reference_id"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def value_digest(value: Any) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    return hashlib.sha256(data).hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts or path.is_symlink():
        raise ValueError(f"Invalid manifest path: {relative}")
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError(f"Missing or external manifest file: {relative}")
    return path


def retained(root: Path) -> set[str]:
    excluded = {".log", ".db", ".sqlite", ".sqlite3"}
    return {
        str(path.relative_to(root)) for path in root.rglob("*")
        if path.is_file() and path.name != "sha256.json" and path.suffix not in excluded
        and "runtime" not in path.relative_to(root).parts
        and not path.name.endswith((".db-wal", ".db-shm"))
    }


def source_files(repo: Path) -> set[str]:
    files = {repo / "pyproject.toml", repo / "uv.lock"}
    for directory in ["scripts", "rl_kyc_task_env", "generator", "baselines", "task/tools", "judge"]:
        files.update((repo / directory).rglob("*.py"))
    return {str(path.relative_to(repo)) for path in files}


def snapshot(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): digest(path) for path in root.rglob("*") if path.is_file()}


class Audit:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.counts: Counter = Counter()

    def check(self, condition: bool, message: str) -> None:
        self.counts["assertions"] += 1
        if not condition:
            self.errors.append(message)

    def hashes(self, root: Path, values: dict[str, str], label: str) -> None:
        for relative, expected in values.items():
            try:
                observed = digest(safe_file(root, relative))
                self.check(observed == expected, f"{label}: hash mismatch {relative}")
            except (OSError, ValueError) as exc:
                self.errors.append(f"{label}: {exc}")
            self.counts[label] += 1


def run(repo: Path, evidence: Path, expected_sources: int) -> dict[str, Any]:
    # These guards precede all imports, document reads, and any generation.
    for name in ["results.json", "sha256.json", "selection.json", "protocol.json"]:
        if not (evidence / name).is_file():
            raise ValueError(f"Completed evidence required before validation: missing {name}")
    if (evidence / "failure.json").exists():
        raise ValueError("Run contains failure.json; refuse to treat it as a completed benchmark")
    audit = Audit()
    checksum_index = load(evidence / "sha256.json")
    frozen = load(evidence / "protocol.json")
    selection = load(evidence / "selection.json")
    results = load(evidence / "results.json")
    audit.check(set(checksum_index) == retained(evidence), "Retained evidence inventory differs from sha256.json")
    audit.hashes(evidence, checksum_index, "retained_file_hashes")
    sources = frozen["sources_sha256"]
    audit.check(len(sources) == expected_sources, f"Expected exactly {expected_sources} frozen source hashes")
    audit.check(set(sources) == source_files(repo), "Current source inventory differs from protocol freeze")
    audit.hashes(repo, sources, "protocol_source_hashes")
    audit.check(digest(evidence / "selected-prompt.txt") == selection["prompt_sha256"], "Selected prompt hash differs")
    audit.check(selection["selected"] == results["selected_prompt"], "Selection identity differs from results")
    audit.check(selection["holdout_generated"] is False and selection["holdout_outputs_inspected"] is False,
                "Selection does not declare pre-holdout freeze")
    audit.check(datetime.fromisoformat(frozen["frozen_at_utc"]) <= datetime.fromisoformat(selection["frozen_at_utc"])
                <= datetime.fromisoformat(results["completed_at_utc"]), "Declared freeze/selection/completion times are out of order")
    # Never execute a changed generator when the source/integrity check has failed.
    if audit.errors:
        return {"passed": False, "counts": dict(audit.counts), "errors": audit.errors,
                "regeneration": "not attempted because integrity checks failed"}

    sys.path.insert(0, str(repo))
    from faker import Faker
    import numpy as np
    from generator import field_sampling, template_specs_private, template_specs_public
    from rl_kyc_task_env.comparison_dataset import generate_split, protocol
    from rl_kyc_task_env.schemas import field_names, validate_prediction

    current_protocol = protocol()
    audit.check(current_protocol == frozen["dataset"], "Dataset protocol, dependencies, sources, schemas, or fonts changed")
    manifests = {split: load(evidence / split / "manifest.json") for split in SEEDS}
    family_sets = {}
    split_summaries = {}
    for split, manifest in manifests.items():
        root = evidence / split
        records = manifest["documents"]
        count = 9 if split == "dev" else 24
        expected_base_count = 9 if split == "dev" else 12
        audit.check(manifest["split"] == split and manifest["seed"] == SEEDS[split], f"{split}: wrong split or seed")
        audit.check(len(records) == count, f"{split}: wrong document count")
        audit.check(manifest["protocol"] == frozen["dataset"], f"{split}: dataset manifest protocol differs from freeze")
        ids = [record["doc_id"] for record in records]
        audit.check(len(set(ids)) == len(ids), f"{split}: duplicate document IDs")
        audit.check(set(ids) == {path.name for path in (root / "inputs").iterdir()}, f"{split}: input inventory mismatch")
        audit.check({f"{doc_id}.json" for doc_id in ids} == {path.name for path in (root / "gold").iterdir()},
                    f"{split}: gold inventory mismatch")
        bases = defaultdict(list)
        family_sets[split] = {record["template"] for record in records}
        null_documents = 0
        for record in records:
            doc_id, schema = record["doc_id"], record["schema_name"]
            directory = root / "inputs" / doc_id
            ocr_path, gold_path = directory / "ocr.json", root / "gold" / f"{doc_id}.json"
            audit.check(digest(ocr_path) == record["ocr_sha256"], f"{doc_id}: OCR hash mismatch")
            audit.check(digest(gold_path) == record["gold_sha256"], f"{doc_id}: gold hash mismatch")
            audit.counts["document_input_and_gold_hashes"] += 2
            audit.check({path.name for path in directory.iterdir()} == {"meta.json", "ocr.json"}, f"{doc_id}: extra model inputs")
            meta = load(directory / "meta.json")
            audit.check(set(meta) == {"doc_id", "schema_name", "num_pages", "language"}, f"{doc_id}: unexpected model metadata")
            audit.check(meta["doc_id"] == doc_id and meta["schema_name"] == schema, f"{doc_id}: mismatched model metadata")
            gold = load(gold_path)
            audit.check(validate_prediction(schema, gold), f"{doc_id}: invalid gold schema")
            missing = [MISSING[schema]] if split == "holdout" and record["base_index"] == 1 else []
            audit.check(record["missing_fields"] == missing, f"{doc_id}: wrong missing-field condition")
            audit.check([key for key, value in gold["fields"].items() if value is None] == missing,
                        f"{doc_id}: null gold does not match declared missing field")
            null_documents += bool(missing)
            # Resample directly through the original constructors, independently of
            # comparison_dataset.sample_fields, to check every untouched gold value.
            rng = np.random.default_rng(record["seed"])
            faker = Faker(["en_US", "en_GB", "en_CA"])
            faker.seed_instance(record["seed"])
            if schema == "government_id":
                original = field_sampling.sample_government_id(rng, faker)
            elif schema == "proof_of_address":
                original = field_sampling.sample_proof_of_address(rng, faker, record["template"])
            else:
                original = field_sampling.sample_payment_receipt(rng, faker)
            fields = dict(original)
            for key in missing:
                fields[key] = ""
            expected_gold = {key: None if key in missing else original[key] for key in field_names(schema)}
            audit.check(gold["fields"] == expected_gold, f"{doc_id}: gold changed beyond the visible blanked field")
            audit.check(value_digest(original) == record["original_fields_sha256"], f"{doc_id}: original fields hash mismatch")
            audit.check(value_digest(fields) == record["rendered_fields_sha256"], f"{doc_id}: pre-render blanked fields hash mismatch")
            builders = template_specs_public.PUBLIC_TEMPLATES if split == "dev" else template_specs_private.PRIVATE_TEMPLATES
            audit.check(value_digest(builders[record["template"]](fields)) == record["rendered_elements_sha256"],
                        f"{doc_id}: template was not rendered from declared blanked fields")
            bases[record["base_id"]].append(record)
        audit.check(len(bases) == expected_base_count == manifest["independent_base_documents"], f"{split}: wrong base count")
        audit.check(len({pair[0]["seed"] for pair in bases.values()}) == expected_base_count, f"{split}: repeated base seeds")
        audit.check(null_documents == (0 if split == "dev" else 12), f"{split}: wrong number of null documents")
        for base_id, pair in bases.items():
            expected_profiles = ["standard_noise"] if split == "dev" else ["clean", "standard_noise"]
            audit.check([item["ocr_profile"] for item in pair] == expected_profiles, f"{base_id}: wrong noise pairing")
            if split == "holdout":
                clean, noisy = pair
                for key in ["schema_name", "base_index", "template", "seed", "ocr_seed", "missing_fields", "gold_sha256",
                            "original_fields_sha256", "rendered_fields_sha256", "rendered_elements_sha256"]:
                    audit.check(clean[key] == noisy[key], f"{base_id}: pair differs in {key}")
                audit.check(clean["ocr_sha256"] != noisy["ocr_sha256"], f"{base_id}: clean/noisy OCR identical")
                audit.counts["validated_clean_noisy_pairs"] += 1
        split_summaries[split] = {"documents": len(records), "independent_bases": len(bases),
                                  "families": len(family_sets[split]), "null_documents": null_documents}
    audit.check(family_sets["dev"].isdisjoint(family_sets["holdout"]), "Dev and holdout share template families")
    audit.check(len(family_sets["dev"]) == 9 and len(family_sets["holdout"]) == 6, "Wrong family counts")

    regenerated = {}
    if not audit.errors:
        with tempfile.TemporaryDirectory(prefix="rl-comparison-verify-") as temporary:
            for split in SEEDS:
                generated_root = Path(temporary) / split
                generated_manifest = generate_split(generated_root, split)
                original_files, repeated_files = snapshot(evidence / split), snapshot(generated_root)
                audit.check(generated_manifest == manifests[split], f"{split}: regenerated manifest differs")
                audit.check(original_files == repeated_files, f"{split}: regenerated file bytes or inventory differ")
                regenerated[split] = {"files": len(repeated_files), "exact_match": original_files == repeated_files}
        audit.hashes(repo, sources, "post_regeneration_source_hashes")
        audit.hashes(evidence, checksum_index, "post_regeneration_evidence_hashes")
    return {"passed": not audit.errors, "counts": dict(audit.counts), "splits": split_summaries,
            "regeneration": regenerated or "not attempted because validation failed", "errors": audit.errors,
            "scope": "File/source integrity, dataset pairing/nulls, and deterministic regeneration; model metrics audited separately."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/workspace/scratch/b33fb38091a9/rl-kyc-task-env"))
    parser.add_argument("--evidence", type=Path, default=Path("/workspace/scratch/b33fb38091a9/rl-comparison-20260913"))
    parser.add_argument("--expected-source-count", type=int, default=42)
    args = parser.parse_args()
    try:
        result = run(args.repo.resolve(), args.evidence.resolve(), args.expected_source_count)
    except Exception as exc:
        result = {"passed": False, "exception": {"type": type(exc).__name__, "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()

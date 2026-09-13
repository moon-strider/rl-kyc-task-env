"""Independent generation checks use test seeds, never the frozen experiment holdout."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest

from generator.template_specs_private import PRIVATE_TEMPLATES
from rl_kyc_task_env import comparison_dataset as dataset
from rl_kyc_task_env.schemas import SCHEMA_NAMES, validate_prediction


def read_json(path: Path):
    return json.loads(path.read_text())


def snapshot(root: Path):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts}


class ComparisonDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        repository = Path(dataset.__file__).resolve().parents[1]
        cls.baseline_roots = [repository / "generator", repository / "baselines",
                              repository / "task" / "public_data", repository / "private"]
        cls.baseline_before = [snapshot(path) for path in cls.baseline_roots]
        cls.old_experiment = repository / "rl_kyc_task_env" / "experiments.py"
        cls.old_experiment_before = cls.old_experiment.read_bytes()
        cls.dev = dataset.generate_split(cls.root / "dev", "dev", seed=313)
        cls.dev_repeat = dataset.generate_split(cls.root / "dev_repeat", "dev", seed=313)
        cls.holdout = dataset.generate_split(cls.root / "holdout", "holdout", seed=919)
        cls.holdout_repeat = dataset.generate_split(cls.root / "holdout_repeat", "holdout", seed=919)

    def test_each_split_is_byte_reproducible(self):
        self.assertEqual(self.dev, self.dev_repeat)
        self.assertEqual(self.holdout, self.holdout_repeat)
        self.assertEqual(snapshot(self.root / "dev"), snapshot(self.root / "dev_repeat"))
        self.assertEqual(snapshot(self.root / "holdout"), snapshot(self.root / "holdout_repeat"))

    def test_disjoint_template_groups_and_independent_bases(self):
        self.assertEqual(len(self.dev["documents"]), 9)
        self.assertEqual(len(self.holdout["documents"]), 24)
        self.assertEqual(self.dev["independent_base_documents"], 9)
        self.assertEqual(self.holdout["independent_base_documents"], 12)
        dev_families = {record["template"] for record in self.dev["documents"]}
        held_families = {record["template"] for record in self.holdout["documents"]}
        self.assertEqual(len(dev_families), 9)
        self.assertEqual(len(held_families), 6)
        self.assertTrue(dev_families.isdisjoint(held_families))
        for schema in SCHEMA_NAMES:
            dev = [record for record in self.dev["documents"] if record["schema_name"] == schema]
            held = [record for record in self.holdout["documents"] if record["schema_name"] == schema]
            self.assertEqual(len(dev), 3)
            self.assertEqual(len(held), 8)
            self.assertEqual({record["ocr_profile"] for record in dev}, {"standard_noise"})
        seeds = {record["base_id"]: record["seed"] for record in self.holdout["documents"]}
        self.assertEqual(len(set(seeds.values())), 12)

    def test_clean_and_noisy_variants_share_exact_gold_and_base(self):
        pairs = {}
        for record in self.holdout["documents"]:
            pairs.setdefault(record["base_id"], []).append(record)
        for base_id, pair in pairs.items():
            with self.subTest(base_id=base_id):
                self.assertEqual(len(pair), 2)
                clean, noisy = pair
                self.assertEqual([record["ocr_profile"] for record in pair], ["clean", "standard_noise"])
                for key in ["seed", "ocr_seed", "template", "missing_fields", "gold_sha256",
                            "original_fields_sha256", "rendered_elements_sha256"]:
                    self.assertEqual(clean[key], noisy[key])
                self.assertNotEqual(clean["ocr_sha256"], noisy["ocr_sha256"])
                self.assertEqual((self.root / "holdout" / "gold" / f"{clean['doc_id']}.json").read_bytes(),
                                 (self.root / "holdout" / "gold" / f"{noisy['doc_id']}.json").read_bytes())

    def test_only_visible_blanked_field_becomes_null_before_ocr(self):
        absent_bases = set()
        for record in self.holdout["documents"]:
            schema, template = record["schema_name"], record["template"]
            gold = read_json(self.root / "holdout" / "gold" / f"{record['doc_id']}.json")
            original = dataset.sample_fields(schema, template, record["seed"])
            missing = record["missing_fields"]
            self.assertTrue(validate_prediction(schema, gold))
            self.assertEqual([key for key, value in gold["fields"].items() if value is None], missing)
            for key, value in gold["fields"].items():
                self.assertEqual(value, None if key in missing else original[key])
            self.assertEqual(len(missing), 1 if record["base_index"] == 1 else 0)
            if not missing:
                continue
            absent_bases.add(record["base_id"])
            field = missing[0]
            before = PRIVATE_TEMPLATES[template](original)
            self.assertTrue(any(original[field] in el.get("text", "") for el in before))
            if record["ocr_profile"] == "clean":
                ocr = read_json(self.root / "holdout" / "inputs" / record["doc_id"] / "ocr.json")
                text = " ".join(token["text"] for token in ocr["pages"][0]["tokens"])
                normalized = re.sub(r"\W", "", text).casefold()
                absent_value = re.sub(r"\W", "", original[field]).casefold()
                self.assertNotIn(absent_value, normalized)
        self.assertEqual(len(absent_bases), 6)

    def test_inputs_expose_only_ocr_and_public_schema_metadata(self):
        for split in ["dev", "holdout"]:
            for directory in (self.root / split / "inputs").iterdir():
                self.assertEqual({path.name for path in directory.iterdir()}, {"meta.json", "ocr.json"})
                meta = read_json(directory / "meta.json")
                self.assertEqual(set(meta), {"doc_id", "schema_name", "num_pages", "language"})
                self.assertNotIn("missing_fields", json.dumps(meta))
                self.assertNotIn("template", json.dumps(meta))
                self.assertEqual(set(read_json(directory / "ocr.json")), {"pages"})

    def test_source_and_protocol_provenance_is_recorded_without_generating_splits(self):
        before = snapshot(self.root)
        protocol = dataset.protocol()
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(protocol["split_seeds"], {"dev": 2026091301, "holdout": 2026091302})
        self.assertIn("public in source", protocol["families_visibility"])
        self.assertIn("rl_kyc_task_env/comparison_dataset.py", protocol["sources_sha256"])
        self.assertTrue(all(len(value) == 64 for value in protocol["sources_sha256"].values()))
        self.assertEqual(set(protocol["versions"]), {"Faker", "numpy", "Pillow"})

    def test_original_baseline_data_and_generator_files_are_unchanged(self):
        self.assertEqual([snapshot(path) for path in self.baseline_roots], self.baseline_before)
        self.assertEqual(self.old_experiment.read_bytes(), self.old_experiment_before)

    def test_refuses_overwrite_and_invalid_split_or_seed(self):
        before = snapshot(self.root / "dev")
        with self.assertRaises(FileExistsError):
            dataset.generate_split(self.root / "dev", "dev", seed=42)
        self.assertEqual(snapshot(self.root / "dev"), before)
        for split, seed in [("unknown", 1), ("dev", -1), ("holdout", True)]:
            with self.subTest(split=split, seed=seed), self.assertRaises(ValueError):
                dataset.generate_split(self.root / "invalid", split, seed=seed)
        self.assertFalse((self.root / "invalid").exists())


if __name__ == "__main__":
    unittest.main()

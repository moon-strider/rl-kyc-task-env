from __future__ import annotations

import unittest

from rl_kyc_task_env.datasets import list_documents, load_json
from rl_kyc_task_env.scoring import aggregate_scores, score_prediction, validate_prediction
from rl_kyc_task_env.schemas import field_names, schema_names


class ScoringTest(unittest.TestCase):
    def test_schema_names_are_stable(self) -> None:
        self.assertEqual(
            schema_names(),
            ("government_id", "proof_of_address", "payment_receipt"),
        )

    def test_field_names_load_from_json_schema(self) -> None:
        self.assertEqual(
            field_names("payment_receipt"),
            (
                "sender_name",
                "recipient_name",
                "amount",
                "currency",
                "payment_date",
                "reference_id",
            ),
        )

    def test_exact_gold_prediction_scores_one(self) -> None:
        record = list_documents("val", limit=1)[0]
        gold = load_json(record.gold_path)
        self.assertTrue(validate_prediction(record.schema_name, gold))
        self.assertEqual(score_prediction(record.schema_name, gold, gold), 1.0)

    def test_aggregate_scores_macro_averages_all_schemas(self) -> None:
        result = aggregate_scores(
            [
                {"schema_name": "government_id", "score": 1.0, "status": "ok"},
                {"schema_name": "proof_of_address", "score": 0.5, "status": "ok"},
                {"schema_name": "payment_receipt", "score": 0.0, "status": "runtime_exception"},
            ],
            include_error_summary=True,
        )
        self.assertEqual(result["score"], 0.5)
        self.assertEqual(result["by_schema"]["government_id"], 1.0)
        self.assertEqual(result["error_summary"], {"runtime_exception": 1})


if __name__ == "__main__":
    unittest.main()

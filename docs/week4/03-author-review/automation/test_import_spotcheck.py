"""Synthetic importer tests only; not human decisions on SprintPulse answers."""
import unittest
from import_spotcheck import validate_and_compare


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.template = [
            {"judgment_id": "SYNTHETIC-1/task_completion", "evaluation_metric": "task_completion",
             "full_saved_answer": "synthetic fixture", "reviewer_decision": "",
             "reviewer_notes": "", "reviewer_alias": "", "reviewed_at": "", "independence_attestation": ""},
            {"judgment_id": "SYNTHETIC-2/memory_context_accuracy", "evaluation_metric": "memory_context_accuracy",
             "full_saved_answer": "synthetic fixture 2", "reviewer_decision": "",
             "reviewer_notes": "", "reviewer_alias": "", "reviewed_at": "", "independence_attestation": ""},
        ]
        self.predictions = {row["judgment_id"]: {"predicted": "PASS"} for row in self.template}

    def signed(self, value="1"):
        rows = [row.copy() for row in self.template]
        rows[0].update(reviewer_decision=value, reviewer_notes="Synthetic test reason, not an actual human finding.",
                       reviewer_alias="synthetic-test-only", reviewed_at="2026-11-11",
                       independence_attestation="Synthetic fixture; not a reviewer sign-off.")
        return rows

    def test_blank_is_pending_not_agreement(self):
        result = validate_and_compare(self.template, self.template, self.predictions)
        self.assertIsNone(result["agreement_fraction_reviewed_only"])
        self.assertEqual(result["reviewed"], 0)

    def test_partial_agreement_uses_reviewed_denominator(self):
        result = validate_and_compare(self.template, self.signed(), self.predictions)
        self.assertEqual(result["agreement_fraction_reviewed_only"], 1)
        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(len(result["pending_judgment_ids"]), 1)

    def test_disagreement_is_explicit(self):
        result = validate_and_compare(self.template, self.signed("0"), self.predictions)
        self.assertEqual(result["agreement_fraction_reviewed_only"], 0)
        self.assertEqual(len(result["disagreements"]), 1)

    def test_changed_answer_rejected(self):
        rows = self.signed()
        rows[0]["full_saved_answer"] = "changed"
        with self.assertRaises(ValueError):
            validate_and_compare(self.template, rows, self.predictions)

    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            validate_and_compare(self.template, [self.template[0], self.template[0]], self.predictions)

    def test_invalid_decision_rejected(self):
        with self.assertRaises(ValueError):
            validate_and_compare(self.template, self.signed("PASS"), self.predictions)

    def test_unsigned_decision_rejected(self):
        rows = self.signed()
        rows[0]["independence_attestation"] = ""
        with self.assertRaises(ValueError):
            validate_and_compare(self.template, rows, self.predictions)

    def test_missing_row_rejected(self):
        with self.assertRaises(ValueError):
            validate_and_compare(self.template, self.signed()[:1], self.predictions)


if __name__ == "__main__":
    unittest.main()

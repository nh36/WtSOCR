import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ocr_signature_evidence_test_module",
    ROOT / "scripts/build_tibetan_latin_ocr_signature_evidence.py",
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class OcrSignatureEvidenceTests(unittest.TestCase):
    def test_atomic_full_target_review_is_learning_evidence(self) -> None:
        operations = module.canonical.edit_operations("Zan", "źan")
        self.assertEqual(
            module.classify_learning(
                "full_token_explicit_review",
                "reviewed_full_target_teaching_evidence",
                operations,
                False,
            ),
            "atomic_reviewed_edit",
        )

    def test_multi_edit_does_not_teach_components_automatically(self) -> None:
        operations = module.canonical.edit_operations("Zan", "źaṅ")
        self.assertEqual(
            module.classify_learning(
                "full_token_explicit_review",
                "reviewed_full_target_teaching_evidence",
                operations,
                False,
            ),
            "reviewed_composed_edit",
        )
        self.assertEqual(
            module.applicable_operations(
                operations, "full_token_explicit_review"
            ),
            [],
        )

    def test_feature_scope_selects_only_reviewed_feature(self) -> None:
        operations = module.canonical.edit_operations("Zan", "źaṅ")
        selected = module.applicable_operations(
            operations, "feature_only_final_nasal"
        )
        self.assertEqual(
            [operation["signature"] for operation in selected],
            ["SUB n→ṅ"],
        )

    def test_superseded_correction_is_not_positive_learning_evidence(self) -> None:
        operations = module.canonical.edit_operations("Zan", "Zaṅ")
        self.assertEqual(
            module.classify_learning(
                "feature_only_final_nasal",
                "supporting_but_derived",
                operations,
                True,
            ),
            "not_signature_learning_evidence",
        )

    def test_six_prior_authorities_are_persistent_evidence_decisions(self) -> None:
        reviewed = module.decisions()
        for signature in (
            "SUB n→ṅ", "SUB h→ṅ", "SUB ń→ṅ",
            "SUB I→l", "SUB Z→ź", "SUB z→ź",
        ):
            self.assertEqual(reviewed[signature]["decision"], "A")

    def test_marker_edit_is_not_tibetan_signature_evidence(self) -> None:
        operations = module.canonical.edit_operations("Ses", "śes")
        self.assertEqual(
            module.classify_learning(
                "marker_only", "not_teaching_evidence", operations, False
            ),
            "structural_or_punctuation_edit",
        )

    def test_unicode_normalized_edit_script(self) -> None:
        composed = "z\u0301"
        operations = module.canonical.edit_operations(composed, "ź")
        self.assertEqual(operations, [])

    def test_generated_registry_uses_decisions_not_frequency(self) -> None:
        outputs = module.build()
        registry = {
            row["operation_signature"]: row for row in outputs["registry"]
        }
        self.assertEqual(
            registry["SUB n→ṅ"]["authorization_status"],
            "authorized_role_conditioned",
        )
        self.assertNotIn(
            registry["SUB o→a"]["authorization_status"],
            {"authorized", "authorized_role_conditioned"},
        )


if __name__ == "__main__":
    unittest.main()

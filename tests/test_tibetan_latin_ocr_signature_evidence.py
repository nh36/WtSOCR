import importlib.util
import csv
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
    @classmethod
    def setUpClass(cls) -> None:
        cls.generated = module.build()

    def test_historical_echo_identity_is_not_reauthorised_positionally(self) -> None:
        self.assertIn(
            ("wts_1_34", "804", "213", "4"),
            module.reviewed_echo_identity_keys(),
        )

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

    def test_nonlearning_and_alternate_only_rows_are_not_positive_support(self) -> None:
        self.assertFalse(
            module.learning_can_support_signature(
                "not_signature_learning_evidence"
            )
        )
        self.assertFalse(
            module.learning_can_support_signature("reviewed_composed_edit")
        )
        self.assertTrue(
            module.learning_can_support_signature("atomic_reviewed_edit")
        )
        self.assertTrue(
            module.learning_can_support_signature("feature_specific_review")
        )

    def test_six_prior_authorities_are_persistent_evidence_decisions(self) -> None:
        reviewed = module.decisions()
        for signature in (
            "SUB n→ṅ", "SUB h→ṅ", "SUB ń→ṅ",
            "SUB I→l", "SUB Z→ź", "SUB z→ź",
        ):
            self.assertEqual(reviewed[signature]["decision"], "A")

    def _row(self, tibetan: str, source: str, **updates):
        row = {
            "tibetan_syllable": tibetan,
            "latin_token": source,
            "zone": "headword_line",
            "context_excerpt": f"{tibetan} {source}",
            "token_boundary_status": "token_boundary_secure",
        }
        row.update(updates)
        return row

    def _registry(self, signature: str):
        return next(
            row for row in self.generated["registry"]
            if row["operation_signature"] == signature
            and row["authorization_status"].startswith("authorized")
        )

    def test_final_n_condition_rejects_nonfinal_operation(self) -> None:
        record = self._registry("SUB n→ṅ")
        applies, reason = module.signature_applies_to_row(
            record, self._row("གང", "gna"), "gṅa"
        )
        self.assertFalse(applies)
        self.assertIn(reason, {
            "source_position_mismatch", "tibetan_role_mismatch",
        })

    def test_final_n_condition_requires_tibetan_coda_ng(self) -> None:
        record = self._registry("SUB n→ṅ")
        applies, reason = module.signature_applies_to_row(
            record, self._row("དོན", "don"), "doṅ"
        )
        self.assertFalse(applies)
        self.assertEqual(reason, "tibetan_role_mismatch")

    def test_final_ng_local_role_gate_does_not_require_full_segmentation(self) -> None:
        record = self._registry("SUB n→ṅ")
        applies, reason = module.signature_applies_to_row(
            record, self._row("གང", "gan"), "gaṅ"
        )
        self.assertTrue(applies, reason)

    def test_zha_condition_rejects_unrelated_tibetan(self) -> None:
        record = self._registry("SUB Z→ź")
        applies, reason = module.signature_applies_to_row(
            record, self._row("ཟ", "Za"), "źa"
        )
        self.assertFalse(applies)
        self.assertEqual(reason, "tibetan_role_mismatch")

    def test_initial_i_condition_rejects_medial_i(self) -> None:
        record = self._registry("SUB I→l")
        applies, reason = module.signature_applies_to_row(
            record, self._row("ལ", "aI"), "al"
        )
        self.assertFalse(applies)
        self.assertEqual(reason, "source_position_mismatch")

    def test_authorized_status_cannot_bypass_boundary_or_domain(self) -> None:
        record = self._registry("SUB n→ṅ")
        applies, reason = module.signature_applies_to_row(
            record, self._row(
                "གང", "gan",
                token_boundary_status="adjacent_transliteration_glyph_uncaptured",
            ), "gaṅ"
        )
        self.assertFalse(applies)
        self.assertEqual(reason, "insecure_token_boundary")
        applies, reason = module.signature_applies_to_row(
            record, self._row(
                "གང", "gan", zone="german_prose",
                context_excerpt="German gan prose",
            ), "gaṅ"
        )
        self.assertFalse(applies)
        self.assertEqual(reason, "domain_mismatch")

    def test_compound_signature_decomposition_is_diagnostic(self) -> None:
        self.assertEqual(
            module.primitive_decomposition("kyani", "kyaṅ", "REPLACE ni→ṅ"),
            ["SUB n→ṅ", "DEL token-final i after n"],
        )

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
        registry = {
            row["operation_signature"]: row for row in self.generated["registry"]
        }
        self.assertEqual(
            registry["SUB n→ṅ"]["authorization_status"],
            "authorized_role_conditioned",
        )
        self.assertNotIn(
            registry["SUB o→a"]["authorization_status"],
            {"authorized", "authorized_role_conditioned"},
        )

    def test_leading_apostrophe_is_extra_initial_material(self) -> None:
        operation = module.canonical.edit_operations("'khoṅ", "khoṅ")[0]
        attributed = module.attribute_edit_to_spans(
            "'khoṅ", "khoṅ", operation, [{
                "target_start": "3", "target_end": "4",
                "tibetan_role": "suffix_coda", "tibetan_feature": "ང",
                "rule_id": "NG",
            }], "ordinary_tibetan_lexical_or_compound",
        )
        self.assertEqual(
            attributed["source_structural_location"],
            "extra_source_material:token_initial",
        )
        self.assertEqual(attributed["target_structural_role"], "none")

    def test_root_substitution_maps_to_root_span(self) -> None:
        operation = module.canonical.edit_operations("kbuṅ", "khuṅ")[0]
        attributed = module.attribute_edit_to_spans(
            "kbuṅ", "khuṅ", operation, [{
                "target_start": "0", "target_end": "2",
                "tibetan_role": "root_consonant", "tibetan_feature": "ཁ",
                "rule_id": "KH",
            }], "ordinary_tibetan_lexical_or_compound",
        )
        self.assertEqual(attributed["target_structural_role"], "root_consonant")
        self.assertEqual(attributed["target_component_rule_id"], "KH")

    def test_kani_signature_ready_is_not_necessarily_final_ready(self) -> None:
        row = next(
            item for item in self.generated["queue"]
            if item["tibetan_syllable"] == "ཀང"
            and item["current_source"] == "kani"
        )
        # The reviewed domain exception must prevent action even though the
        # conditioned final-ni signature itself is authorised.
        self.assertEqual(row["ocr_signature_ready"], "yes")
        self.assertEqual(row["final_action_ready"], "no")

    def test_noncanonical_role_and_unknown_condition_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "noncanonical Tibetan role"):
            module.validate_signature_condition({
                "signature": "BAD", "tibetan_role": "root",
                "source_position_type": "", "target_position_type": "",
                "domain_condition": "", "canonical_target_required": "yes",
                "aligned_tibetan_required": "yes",
            })
        with self.assertRaisesRegex(ValueError, "malformed forbidden"):
            module.validate_signature_condition({
                "signature": "BAD", "tibetan_role": "",
                "source_position_type": "", "target_position_type": "",
                "domain_condition": "", "canonical_target_required": "yes",
                "aligned_tibetan_required": "yes",
                "forbidden_tibetan_role_features": "root_consonant",
            })
        with self.assertRaisesRegex(ValueError, "unknown source_position_type"):
            module.validate_signature_condition({
                "signature": "BAD", "tibetan_role": "",
                "source_position_type": "approximately_initial",
                "target_position_type": "", "domain_condition": "",
                "canonical_target_required": "yes",
                "aligned_tibetan_required": "yes",
            })

    def test_root_child_requires_exact_root_and_role_span(self) -> None:
        record = next(
            row for row in self.generated["registry"]
            if row["signature_id"] == "ROOT_KB_TO_KH"
        )
        applies, reason = module.signature_applies_to_row(
            record, self._row("ཐུང", "kbuṅ"), "khuṅ"
        )
        self.assertFalse(applies)
        self.assertEqual(reason, "tibetan_role_mismatch")

    def test_apostrophe_child_enforces_extra_initial_and_achung_block(self) -> None:
        record = next(
            row for row in self.generated["registry"]
            if row["signature_id"]
            == "INITIAL_STRAIGHT_APOSTROPHE_EXTRA_NO_ACHUNG"
        )
        applies, reason = module.signature_applies_to_row(
            record, self._row("འཁོར", "'khor"), "khor"
        )
        self.assertFalse(applies)
        self.assertEqual(reason, "forbidden_tibetan_feature")
        applies, reason = module.signature_applies_to_row(
            record, self._row("ཁོར", "kh'or"), "khor"
        )
        self.assertFalse(applies)
        self.assertIn(reason, {
            "source_context_mismatch", "source_position_mismatch",
            "source_structural_location_mismatch",
        })

    def test_missing_r_children_enforce_distinct_roles(self) -> None:
        subjoined = next(
            row for row in self.generated["registry"]
            if row["signature_id"] == "INS_R_SUBJOINED"
        )
        superscript = next(
            row for row in self.generated["registry"]
            if row["signature_id"] == "INS_R_SUPERSCRIPT"
        )
        applies, _ = module.signature_applies_to_row(
            subjoined, self._row("གྲི", "gi"), "gri"
        )
        self.assertTrue(applies)
        applies, reason = module.signature_applies_to_row(
            superscript, self._row("གྲི", "gi"), "gri"
        )
        self.assertFalse(applies)
        self.assertEqual(reason, "tibetan_role_mismatch")

    def test_conditioned_child_does_not_inherit_parent_evidence(self) -> None:
        child = next(
            row for row in self.generated["registry"]
            if row["signature_id"] == "ROOT_KB_TO_KH"
        )
        self.assertEqual(child["conditioned_alternate_support"], "0")
        self.assertGreater(
            int(child["parent_operation_alternate_support"]), 0
        )

    def test_historical_only_family_has_zero_active_yield(self) -> None:
        with (
            ROOT / "data/tibetan_latin_active_historical_queue_summary.tsv"
        ).open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        gloss = next(
            row for row in rows
            if row["queue_category"] == "gloss_alignment_noise"
        )
        self.assertGreater(int(gloss["historical_only_families"]), 0)
        self.assertEqual(gloss["current_exact_occurrences"], "0")

    def test_no_layout_candidate_is_implicitly_alignment_authority(self) -> None:
        with (
            ROOT / "data/tibetan_latin_alignment_rescue_exact.tsv"
        ).open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertTrue(rows)
        self.assertFalse(any(
            row["upgrade_authorized"] == "yes" for row in rows
        ))


if __name__ == "__main__":
    unittest.main()

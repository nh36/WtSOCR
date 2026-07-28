import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_tibetan_latin_syllable_concordance.py"
SPEC = importlib.util.spec_from_file_location("syllable_concordance_test", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class SyllableConcordanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        outputs = module.build()
        cls.concordance, cls.canonical, cls.features, cls.outliers, cls.confusions = outputs[:5]
        cls.teaching = outputs[5]

    def test_exact_tibetan_syllable_is_the_key(self) -> None:
        rows = [r for r in self.concordance if r["tibetan_syllable"] == "ཞང"]
        self.assertTrue(any(r["latin_form"] == "źaṅ" for r in rows))

    def test_superseded_target_does_not_teach_canonical_form(self) -> None:
        row = next(r for r in self.canonical if r["tibetan_syllable"] == "ཞང")
        self.assertNotIn("Zaṅ", row["canonical_forms"].split(";"))
        self.assertEqual(row["canonical_forms"], "źaṅ")

    def test_frequency_alone_does_not_create_canonical_form(self) -> None:
        downgraded = [
            r for r in self.canonical
            if r["canonical_confidence_tier"] in {"provisional", "unresolved"}
            and any(
                int(c["current_clean_occurrences"]) > 3
                for c in self.concordance
                if c["tibetan_syllable"] == r["tibetan_syllable"]
            )
        ]
        self.assertTrue(downgraded)

    def test_feature_only_reviews_are_not_full_target_authorities(self) -> None:
        final_only = [
            r for r in self.concordance
            if "feature_only_final_nasal" in r["correction_evidence_scope"]
        ]
        self.assertTrue(final_only)
        self.assertTrue(any(
            "feature_only_final_nasal:" in r["correction_evidence_scope"]
            for r in final_only
        ))

    def test_derived_corrections_do_not_self_teach(self) -> None:
        row = next(
            r for r in self.concordance
            if r["tibetan_syllable"] == "བཞི" and r["latin_form"] == "bźi"
        )
        self.assertIn("supporting_but_derived", row["canonical_teaching_breakdown"])

    def test_reviewed_ocr_source_is_preserved_but_cannot_teach(self) -> None:
        row = next(
            r for r in self.teaching
            if r["tibetan_syllable"] == "ཀྱང"
            and r["latin_form"] == "kyani"
        )
        self.assertEqual(row["provenance_class"], "historical_observation")
        self.assertEqual(
            row["canonical_teaching_status"], "not_teaching_evidence"
        )

    def test_observed_forms_are_distinct_from_credible_competitors(self) -> None:
        row = next(r for r in self.canonical if r["tibetan_syllable"] == "ཁང")
        self.assertIn("Bank", row["observed_other_forms"])
        self.assertNotIn(
            "Bank", row["credible_competing_transcriptions"].split(";")
        )

    def test_provenance_is_reconstructed(self) -> None:
        self.assertTrue(any(
            "historical_google_adopted" in r["provenance_breakdown"]
            or "historical_other_postprocess" in r["provenance_breakdown"]
            for r in self.concordance
        ))
        self.assertTrue(any(
            int(r["google_adopted_occurrences"]) > 0
            for r in self.concordance
        ))

    def test_foreign_domain_never_teaches_empirical_canonical(self) -> None:
        self.assertTrue(all(
            row["canonical_teaching_status"] !=
            "independent_teaching_evidence"
            for row in self.teaching
            if row["domain_context"] !=
            "ordinary_tibetan_lexical_or_compound"
        ))

    def test_edit_operation_taxonomy(self) -> None:
        self.assertEqual(
            module.edit_operations("bZi", "bźi")[0]["operation_type"],
            "single_diacritic_or_case_confusion",
        )
        self.assertEqual(
            module.edit_operations("Si", "si")[0]["operation_type"],
            "single_diacritic_or_case_confusion",
        )
        self.assertEqual(
            module.edit_operations("gli", "gliṅ")[0]["operation_type"],
            "single_character_insertion",
        )
        self.assertEqual(
            module.edit_operations("glliṅ", "gliṅ")[0]["operation_type"],
            "single_character_deletion",
        )
        self.assertEqual(module.edit_operations("s\u0301", "ś"), [])
        self.assertEqual(
            module.edit_category(module.edit_operations("In", "lṅ")),
            "multiple_recognised_edits",
        )

    def test_z_to_zacute_is_aggregated_across_syllables(self) -> None:
        rows = {
            r["operation_signature"]: r for r in self.confusions
        }
        self.assertGreaterEqual(
            int(rows["SUB Z→ź"]["independent_tibetan_syllables"]), 3
        )
        self.assertEqual(
            rows["SUB Z→ź"]["authorization_status"],
            "authorized_exact_tibetan_conditioned",
        )

    def test_competing_forms_require_independent_support(self) -> None:
        ambiguous = [
            r for r in self.canonical
            if r["canonical_confidence_tier"] == "ambiguous"
        ]
        self.assertTrue(ambiguous)
        self.assertTrue(all(
            r["competing_support"] or r["supporting_forms"]
            for r in ambiguous
        ))

    def test_canonical_downgrade_does_not_remove_active_override(self) -> None:
        dran = next(
            r for r in self.canonical if r["tibetan_syllable"] == "དྲང"
        )
        if dran["canonical_confidence_tier"] not in {
            "canonical_reviewed", "canonical_independent_strong"
        }:
            overrides = module.integrity.read_tsv(
                module.integrity.OVERRIDES_PATH
            )
            self.assertTrue(any(
                r["to_token"] == "draṅ" for r in overrides
            ))


if __name__ == "__main__":
    unittest.main()

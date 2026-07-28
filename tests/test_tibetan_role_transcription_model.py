import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "role_model_under_test",
    ROOT / "scripts/build_tibetan_role_transcription_model.py",
)
assert SPEC and SPEC.loader
role_model = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = role_model
SPEC.loader.exec_module(role_model)


class TibetanRoleParserTests(unittest.TestCase):
    def test_parse_does_not_consult_latin(self):
        parsed = role_model.parse_tibetan_syllable("གཞུང")
        self.assertEqual(parsed["prefix"], "ག")
        self.assertEqual(parsed["root_consonant"], "ཞ")
        self.assertEqual(parsed["vowel"], "u")
        self.assertEqual(parsed["suffix_coda"], "ང")
        self.assertEqual(parsed["role_parse_status"], "fully_resolved")

    def test_superscript_and_subjoined_are_distinguished(self):
        superscript = role_model.parse_tibetan_syllable("སྐོང")
        self.assertEqual(superscript["superscript"], "ས")
        self.assertEqual(superscript["root_consonant"], "ཀ")
        medial = role_model.parse_tibetan_syllable("ཀྱང")
        self.assertEqual(medial["root_consonant"], "ཀ")
        self.assertEqual(medial["subjoined_consonants"], "ཡ")

    def test_ambiguous_root_is_not_guessed(self):
        parsed = role_model.parse_tibetan_syllable("གད")
        self.assertIn(
            parsed["role_parse_status"],
            {"ambiguous_root", "fully_resolved"},
        )
        if parsed["role_parse_status"] == "ambiguous_root":
            self.assertTrue(parsed["ambiguous_root_candidates"])

    def test_supported_and_unsupported_vowel_signs_are_distinguished(self):
        self.assertEqual(
            role_model.parse_tibetan_syllable("བ")["vowel"], "a"
        )
        for syllable, vowel in (
            ("བི", "i"), ("བུ", "u"), ("བེ", "e"), ("བོ", "o"),
        ):
            self.assertEqual(
                role_model.parse_tibetan_syllable(syllable)["vowel"], vowel
            )
        for syllable in ("བཱ", "བཾ", "བཿ", "བིུ"):
            self.assertEqual(
                role_model.parse_tibetan_syllable(syllable)[
                    "role_parse_status"
                ],
                "unsupported_orthographic_sign",
            )

    def test_unknown_combining_sign_is_never_default_a(self):
        parsed = role_model.parse_tibetan_syllable("བ\u0f39")
        self.assertEqual(
            parsed["role_parse_status"], "unsupported_orthographic_sign"
        )


class FeatureCompositionTests(unittest.TestCase):
    def test_reviewed_rules_compose_unique_target(self):
        rules = {
            ("prefix", "ག"): {"latin_realization": "g", "rule_id": "P"},
            ("root_consonant", "ཞ"): {
                "latin_realization": "ź", "rule_id": "R",
            },
            ("vowel", "u"): {"latin_realization": "u", "rule_id": "V"},
            ("suffix_coda", "ང"): {
                "latin_realization": "ṅ", "rule_id": "S",
            },
        }
        target, ids, missing = role_model.compose(
            role_model.parse_tibetan_syllable("གཞུང"), rules
        )
        self.assertEqual(target, "gźuṅ")
        self.assertFalse(missing)
        self.assertEqual(ids, ["P", "R", "V", "S"])

    def test_missing_feature_blocks_composition(self):
        target, _ids, missing = role_model.compose(
            role_model.parse_tibetan_syllable("གཞུང"),
            {("suffix_coda", "ང"): {
                "latin_realization": "ṅ", "rule_id": "S",
            }},
        )
        self.assertEqual(target, "")
        self.assertIn("root_consonant:ཞ", missing)

    def test_cluster_condition_prevents_wrong_reconstruction(self):
        rules = {
            ("prefix", "ག"): {"latin_realization": "g", "rule_id": "P"},
            ("root_consonant", "ཡ"): {
                "latin_realization": "y", "rule_id": "R",
            },
            ("vowel", "o"): {"latin_realization": "o", "rule_id": "V"},
        }
        target, _ids, missing = role_model.compose(
            role_model.parse_tibetan_syllable("གཡོ"), rules
        )
        self.assertEqual(target, "")
        self.assertIn("cluster:ག+ཡ:conditioned_separator_unresolved", missing)

    def test_aspirated_root_subjoined_cluster_requires_unit_rule(self):
        rules = {
            ("root_consonant", "ཐ"): {
                "latin_realization": "th", "rule_id": "TH",
            },
            ("subjoined_consonants", "ར"): {
                "latin_realization": "r", "rule_id": "R",
            },
            ("vowel", "o"): {"latin_realization": "o", "rule_id": "O"},
            ("suffix_coda", "བ"): {
                "latin_realization": "b", "rule_id": "B",
            },
        }
        target, _ids, missing = role_model.compose(
            role_model.parse_tibetan_syllable("ཐྲོབ"), rules
        )
        self.assertEqual(target, "")
        self.assertIn(
            "cluster:root_ཐ+subjoined:structural_realization_unresolved",
            missing,
        )

    def test_feature_composed_edges_are_non_teaching(self):
        graph = [{
            "from_node": "feature_rule:R",
            "edge_type": "composes",
            "to_node": "canonical_feature_composed:X",
            "evidence_identity": "X",
            "teaching_allowed": "no",
        }]
        role_model.validate_no_cycles(graph)

    def test_cycle_detection_rejects_teaching_cycle(self):
        graph = [
            {
                "from_node": "A", "edge_type": "teaches", "to_node": "B",
                "evidence_identity": "1", "teaching_allowed": "yes",
            },
            {
                "from_node": "B", "edge_type": "teaches", "to_node": "A",
                "evidence_identity": "2", "teaching_allowed": "yes",
            },
        ]
        with self.assertRaises(ValueError):
            role_model.validate_no_cycles(graph)

    def test_insertion_delta_is_not_complete_root_realization(self):
        operation = {
            "operation_type": "single_character_insertion",
            "source_span": "",
            "target_span": "h",
        }
        self.assertEqual(
            role_model.classify_contrast_evidence(
                "root_consonant", "ཀ", "ཁ", operation
            ),
            "contrastive_delta_only",
        )

    def test_strict_leave_one_out_recomputes_threshold(self):
        original_cache = role_model._TEACHING_DIVERSITY_CACHE
        try:
            role_model._TEACHING_DIVERSITY_CACHE = {
                "A": ({"v1"}, {"v1:p1"}),
                "B": ({"v1"}, {"v1:p2"}),
                "C": ({"v2"}, {"v2:p1"}),
                "D": ({"v2"}, {"v2:p2"}),
            }
            base = {
                "authority_basis": "empirical_corpus",
                "strong_canonical_syllables": "A;B;C",
                "minimal_pair_support": (
                    "A:x↔B:y || A:x↔C:z || B:y↔C:z"
                ),
                "evidence_kind": "full_realization_isolated",
                "competing_realizations": "",
            }
            self.assertFalse(role_model.strict_rule_available(base, "A"))
            expanded = {
                **base,
                "strong_canonical_syllables": "A;B;C;D",
                "minimal_pair_support": (
                    "A:x↔B:y || A:x↔C:z || B:y↔C:z || "
                    "B:y↔D:q || C:z↔D:q"
                ),
            }
            self.assertTrue(
                role_model.strict_rule_available(expanded, "A")
            )
        finally:
            role_model._TEACHING_DIVERSITY_CACHE = original_cache

    def test_single_unknown_residual_isolates_complete_digraph(self):
        rules = {
            ("vowel", "a"): {
                "latin_realization": "a", "rule_id": "V",
                "authority_basis": "explicit_review",
            },
            ("suffix_coda", "ང"): {
                "latin_realization": "ṅ", "rule_id": "S",
                "authority_basis": "explicit_review",
            },
        }
        role, feature, residual, _dependencies, status = (
            role_model.isolate_single_unknown_residual(
                role_model.parse_tibetan_syllable("ཁང"),
                "khaṅ", rules, "ཁང",
            )
        )
        self.assertEqual((role, feature, residual), (
            "root_consonant", "ཁ", "kh",
        ))
        self.assertEqual(status, "single_unknown_residual_isolated")

    def test_two_unknown_roles_reject_residual_induction(self):
        role, _feature, _residual, _dependencies, status = (
            role_model.isolate_single_unknown_residual(
                role_model.parse_tibetan_syllable("གཞུང"),
                "gźuṅ", {}, "གཞུང",
            )
        )
        self.assertEqual(role, "")
        self.assertEqual(status, "multiple_unknown_roles")

    def test_known_ocr_source_is_not_positive_target_support(self):
        channel, authorized = role_model.target_support_channel(
            "བ", "ba", [{
                "tibetan_syllable": "བ", "latin_form": "ba",
                "canonical_teaching_status": "not_teaching_evidence",
                "domain_context": "ordinary_tibetan_lexical_or_compound",
            }], feature_complete=True,
        )
        self.assertEqual(channel, "nonadmissible_observation")
        self.assertFalse(authorized)


if __name__ == "__main__":
    unittest.main()

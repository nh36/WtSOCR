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


if __name__ == "__main__":
    unittest.main()

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_tibetan_latin_integrity.py"
SPEC = importlib.util.spec_from_file_location("tibetan_latin_integrity_test", SCRIPT)
assert SPEC and SPEC.loader
integrity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(integrity)


class TibetanLatinIntegrityTests(unittest.TestCase):
    def test_registry_parses_reviewed_and_ambiguous_rules(self) -> None:
        rows = integrity.load_registry()
        by_feature = {row["tibetan_feature"]: row for row in rows}
        self.assertEqual(by_feature["ཞ"]["expected_latin_feature"], "ź")
        self.assertEqual(by_feature["ཞ"]["review_status"], "reviewed")
        self.assertEqual(by_feature["ཤ"]["review_status"], "ambiguous")

    def test_corpus_conditioned_zha_feature(self) -> None:
        self.assertEqual(
            integrity.token_integrity("ཞང", "źaṅ")["integrity_status"],
            "transcription_integrity_pass",
        )
        self.assertEqual(
            integrity.token_integrity("ཞང", "Zaṅ")["integrity_status"],
            "nonfinal_feature_mismatch",
        )
        self.assertEqual(
            integrity.token_integrity("ཞང", "Zan")["integrity_status"],
            "multiple_feature_mismatches",
        )
        self.assertEqual(
            integrity.token_integrity("ཞེང", "Zeṅ")["integrity_pass"], "no"
        )

    def test_no_global_ascii_z_replacement(self) -> None:
        result = integrity.token_integrity("ཀ", "Zeit")
        self.assertEqual(result["integrity_status"], "insufficient_feature_coverage")
        self.assertEqual(result["violated"], "")
        self.assertEqual(result["known_feature_violation"], "no")
        self.assertEqual(result["feature_coverage"], "none")
        self.assertEqual(result["transcription_gateway_status"], "unresolved")
        self.assertEqual(result["integrity_pass"], "no")

    def test_final_ng_stem_gate_is_separate(self) -> None:
        self.assertEqual(
            integrity.token_integrity("དྲང", "draṅ")["integrity_pass"], "yes"
        )
        self.assertEqual(
            integrity.token_integrity("དྲང", "dran")["integrity_status"],
            "final_feature_mismatch_only",
        )

    def test_reviewed_exception_overrides_missing_feature_coverage(self) -> None:
        result = integrity.token_integrity("ཁོང", "kboṅ")
        self.assertEqual(result["transcription_exception_status"],
                         "source_variant_requires_manual_review")
        self.assertEqual(result["transcription_gateway_status"], "blocked")

    def test_bzhi_root_feature_family_is_exact_and_not_global(self) -> None:
        line = next(
            row["line_text"]
            for row in integrity.read_tsv(
                ROOT / "release/current/qa/wts_1_34/wts_1_34_line_zones.tsv"
            )
            if row["page"] == "35" and row["line"] == "206"
        )
        self.assertIn("ka chen bźi", line)
        self.assertNotIn("ka chen bzi", line)
        unrelated = integrity.token_integrity("ཀ", "bZi")
        self.assertNotEqual(
            unrelated["transcription_gateway_status"], "pass"
        )

    def test_role_parser_does_not_claim_full_transliteration(self) -> None:
        roles = integrity.tibetan_roles("གཞུང")
        self.assertEqual(roles["root_consonant"], "ཞ")
        self.assertEqual(roles["suffix_coda"], "ང")
        self.assertEqual(roles["orthographic_role_status"], "partial")

    def test_supersession_validator_requires_effective_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overrides = root / "overrides.tsv"
            supersessions = root / "supersessions.tsv"
            with overrides.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "volume", "page", "line", "token_index",
                        "from_token", "to_token", "reason", "evidence",
                        "review_note",
                    ],
                    delimiter="\t",
                )
                writer.writeheader()
                writer.writerow({
                    "volume": "v", "page": "1", "line": "2",
                    "token_index": "1", "from_token": "Zan",
                    "to_token": "źaṅ", "reason": "reviewed",
                })
            with supersessions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "original_batch", "volume", "page", "line",
                        "token_index", "tibetan_syllable", "original_source",
                        "old_target", "superseding_target",
                        "supersession_reason", "evidence",
                        "superseding_commit", "status",
                    ],
                    delimiter="\t",
                )
                writer.writeheader()
                writer.writerow({
                    "volume": "v", "page": "1", "line": "2",
                    "token_index": "1", "original_source": "Zan",
                    "superseding_target": "źaṅ", "status": "active",
                })
            old_overrides = integrity.OVERRIDES_PATH
            old_supersessions = integrity.SUPERSESSIONS_PATH
            try:
                integrity.OVERRIDES_PATH = overrides
                integrity.SUPERSESSIONS_PATH = supersessions
                integrity.validate_supersessions()
            finally:
                integrity.OVERRIDES_PATH = old_overrides
                integrity.SUPERSESSIONS_PATH = old_supersessions


if __name__ == "__main__":
    unittest.main()

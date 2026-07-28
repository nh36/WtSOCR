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
        cls.concordance, cls.canonical, cls.features, cls.outliers, cls.confusions = (
            module.build()
        )

    def test_exact_tibetan_syllable_is_the_key(self) -> None:
        rows = [r for r in self.concordance if r["tibetan_syllable"] == "ཞང"]
        self.assertTrue(any(r["latin_form"] == "źaṅ" for r in rows))

    def test_superseded_target_does_not_teach_canonical_form(self) -> None:
        row = next(r for r in self.canonical if r["tibetan_syllable"] == "ཞང")
        self.assertNotIn("Zaṅ", row["canonical_forms"].split(";"))
        self.assertEqual(row["canonical_forms"], "źaṅ")

    def test_frequency_alone_does_not_create_canonical_form(self) -> None:
        unresolved = [
            r for r in self.canonical
            if r["canonical_status"] == "unresolved"
            and any(
                int(c["current_clean_occurrences"]) > 3
                for c in self.concordance
                if c["tibetan_syllable"] == r["tibetan_syllable"]
            )
        ]
        self.assertTrue(unresolved)

    def test_feature_only_reviews_are_not_full_target_authorities(self) -> None:
        final_only = [
            r for r in self.concordance
            if "final_nasal_only" in r["correction_evidence_scope"]
        ]
        self.assertTrue(final_only)
        self.assertTrue(any(
            r["correction_evidence_scope"] == "final_nasal_only"
            for r in final_only
        ))


if __name__ == "__main__":
    unittest.main()

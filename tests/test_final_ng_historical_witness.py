import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_final_ng_historical_witness.py"
SPEC = importlib.util.spec_from_file_location("final_ng_historical_witness", SCRIPT)
assert SPEC and SPEC.loader
historical = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = historical
SPEC.loader.exec_module(historical)


class FinalNgHistoricalWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = historical.build_historical_audit(
            historical.DEFAULT_BASELINE
        )

    def test_baseline_sha_is_exact_and_resolvable(self) -> None:
        self.assertEqual(
            historical.DEFAULT_BASELINE,
            "6322c7255cfba2fcfaf678cec656e65496ed5f12",
        )
        self.assertIsNotNone(
            historical.git_show(
                historical.DEFAULT_BASELINE,
                "release/current/manifest.md",
            )
        )

    def test_pilot_anchors_precede_family_campaign(self) -> None:
        expected = {
            ("ཀྲོང", "kron", "kroṅ"): ("wts_9_m", "302", "20", "2"),
            ("རྟིང", "rtin", "rtiṅ"): ("wts_8_b", "252", "37", "3"),
            ("བགྲང", "bgran", "bgraṅ"): ("wts_8_b", "22", "12", "3"),
        }
        for family, location in expected.items():
            row = next(
                item for item in self.rows
                if (
                    item["tibetan_syllable"],
                    item["source_variant"],
                    item["target"],
                ) == family
            )
            self.assertEqual(row["historical_anchor_present"], "yes")
            self.assertEqual(
                (
                    row["historical_volume"], row["historical_page"],
                    row["historical_line"], row["historical_token_index"],
                ),
                location,
            )
            self.assertTrue(
                row["historical_anchor_provenance_class"].startswith(
                    "historical_pre_family_"
                )
            )

    def test_reviewed_target_propagation_is_exact_signature_only(self) -> None:
        rows = historical.build_reviewed_target_audit()
        eligible = {
            (row["tibetan_syllable"], row["source_variant"], row["target"])
            for row in rows
            if row["eligibility"]
            == "reviewed_same_tibetan_target_final_nasal_only"
        }
        self.assertEqual(
            eligible,
            {
                ("གཞུང", "gźuń", "gźuṅ"),
                ("ལྗང", "ldan", "ldaṅ"),
            },
        )
        self.assertNotIn(("གཞུང", "gun", "gźuṅ"), eligible)
        self.assertNotIn(("ལྗང", "lan", "ldaṅ"), eligible)


if __name__ == "__main__":
    unittest.main()

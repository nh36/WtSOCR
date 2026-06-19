import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_tibetan_cleanup_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("build_tibetan_cleanup_diagnostics", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Could not load build_tibetan_cleanup_diagnostics module from {SCRIPT_PATH}")
diag = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diag
SPEC.loader.exec_module(diag)


class TibetanCleanupDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = diag.load_sigla_registry(ROOT / "data" / "sigla_registry.tsv")

    def test_dnos_target_prefers_dngos_not_google_dnyos(self) -> None:
        row = {
            "page": "68",
            "line": "18",
            "token_index": "7",
            "base_token": "dnos",
            "alternate_token": "dños",
            "reason": "blocked_alternate_witness_wrong_nasal_dnos",
            "base_line": "chos dnos po'i mtshan nyid",
            "alternate_line": "chos dños po'i mtshan nyid",
        }

        candidate = diag.classify_google_row(row, "wts_9_m", self.registry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["candidate_family"], "dngos_family")
        self.assertEqual(candidate["proposed_target"], "dṅos")
        self.assertNotEqual(candidate["proposed_target"], "dños")
        self.assertEqual(candidate["suggested_action"], "exact_promotion_candidate")

    def test_gna_khri_is_exact_candidate(self) -> None:
        candidate = diag.classify_tibetan_token("gNa-khri", "rgyal po gNa-khri btsan po'i lo rgyus")

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["candidate_family"], "gña_khri_family")
        self.assertEqual(candidate["proposed_target"], "gÑa-khri")
        self.assertEqual(candidate["suggested_action"], "exact_promotion_candidate")

    def test_laa_stacked_nasal_damage_is_source_review_only(self) -> None:
        candidate = diag.classify_tibetan_token("la'añń", "skad cig la'añń de bzhin du")

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["candidate_family"], "stacked_nasal_damage")
        self.assertEqual(candidate["proposed_target"], "")
        self.assertEqual(candidate["suggested_action"], "source_review")

    def test_vist_variants_are_sigla_for_visesastavatika(self) -> None:
        for token in ["Vi$T", "VisT"]:
            info = diag.classify_siglum_token(token, "(Vi$T 42; VisT 17)", self.registry)
            self.assertIsNotNone(info)
            self.assertEqual(info["canon"], "ViśT")
            self.assertEqual(info["work_title"], "Viśeṣastavatīkā source")
            self.assertEqual(info["suggested_action"], "siglum_policy_review")

    def test_plain_german_words_are_not_unregistered_sigla(self) -> None:
        for token in ["die", "der", "verlichen"]:
            info = diag.classify_siglum_token(token, f"({token} steht in deutschem Kontext)", self.registry)
            self.assertIsNone(info)

    def test_lowercase_ins_is_not_registered_siglum_in_german_prose(self) -> None:
        info = diag.classify_siglum_token("ins", "chen und betrachte sie bis ins Mark", self.registry)

        self.assertIsNone(info)

    def test_registered_ins_siglum_keeps_case_sensitive_canonical_match(self) -> None:
        info = diag.classify_siglum_token("Ins", "(Ins 12,3)", self.registry)

        self.assertIsNotNone(info)
        self.assertEqual(info["canon"], "Ins")
        self.assertEqual(info["suggested_action"], "already_canonical_siglum")

    def test_registered_dollar_siglum_still_maps_to_canonical_form(self) -> None:
        info = diag.classify_siglum_token("L$dz", "(L$dz 84,6)", self.registry)

        self.assertIsNotNone(info)
        self.assertEqual(info["canon"], "Lśdz")
        self.assertEqual(info["suggested_action"], "siglum_policy_review")

    def test_siglum_google_row_is_not_tibetan_candidate(self) -> None:
        row = {
            "page": "52",
            "line": "35",
            "token_index": "4",
            "base_token": "VisT",
            "alternate_token": "VisṬ",
            "reason": "alternate_witness_unresolved",
            "base_line": "cf. VisT, p. 12",
            "alternate_line": "cf. VisṬ, p. 12",
        }

        candidate = diag.classify_google_row(row, "wts_9_m", self.registry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["candidate_family"], "citation_or_siglum")
        self.assertEqual(candidate["proposed_target"], "ViśT")
        self.assertEqual(candidate["suggested_action"], "siglum_policy_review")

    def test_german_prose_suppresses_tibetan_token_scan(self) -> None:
        candidate = diag.classify_tibetan_token("dnos", "Das ist ein dnos und der Text ist deutsch.")

        self.assertIsNone(candidate)


if __name__ == "__main__":
    unittest.main()

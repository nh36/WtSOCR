import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast


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

    def test_reviewed_dollar_sigla_prefer_s_caron_canonical_forms(self) -> None:
        examples = {
            "Bu-$z": "Bu-śz",
            "Bu-Sz": "Bu-śz",
            "G$-H": "Gś-H",
            "Gs-H": "Gś-H",
            "Y$": "Yś",
            "Ys": "Yś",
        }

        for token, expected in examples.items():
            with self.subTest(token=token):
                info = diag.classify_siglum_token(token, f"({token} 51,3)", self.registry)

                self.assertIsNotNone(info)
                self.assertEqual(info["canon"], expected)
                self.assertEqual(info["suggested_action"], "siglum_policy_review")

    def test_plain_ys_variant_needs_siglum_context(self) -> None:
        info = diag.classify_siglum_token(
            "Ys",
            "Ys steht hier nur als Zeichenfolge in einem deutschen Satz.",
            self.registry,
        )

        self.assertIsNone(info)

    def test_plain_gs_siglum_remains_distinct_from_gs_h_family(self) -> None:
        info = diag.classify_siglum_token("Gs", "(Gs 93a)", self.registry)

        self.assertIsNotNone(info)
        self.assertEqual(info["canon"], "Gs")
        self.assertEqual(info["suggested_action"], "already_canonical_siglum")

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

    def test_tibetan_script_ng_witness_identifies_gang_and_dang(self) -> None:
        line = "གང་དང་ཡང་ gan dan yani \\gan yan."
        gan = diag.classify_tibetan_script_ng_token("gan", line)
        dan = diag.classify_tibetan_script_ng_token("dan", line)

        self.assertIsNotNone(gan)
        self.assertIsNotNone(dan)
        gan = cast(dict[str, str], gan)
        dan = cast(dict[str, str], dan)
        self.assertEqual(gan["proposed_target"], "gaṅ")
        self.assertEqual(gan["reference_marker_source"], "")
        self.assertEqual(gan["reference_marker_target"], "")
        self.assertEqual(gan["base_source_token"], "gan")
        self.assertEqual(gan["base_proposed_target"], "gaṅ")
        self.assertEqual(gan["tibetan_witness"], "གང")
        self.assertEqual(dan["proposed_target"], "daṅ")
        self.assertEqual(dan["tibetan_witness"], "དང")

    def test_tibetan_script_ng_witness_handles_prefixed_t_and_suppresses_unwitnessed(self) -> None:
        line = "གང་དང་གང་ gan dan gan Tgan Igan \\gan gan."
        tgan = diag.classify_tibetan_script_ng_token("Tgan", line)
        igan = diag.classify_tibetan_script_ng_token("Igan", line)
        slash_gan = diag.classify_tibetan_script_ng_token("\\gan", line)

        self.assertIsNotNone(tgan)
        tgan = cast(dict[str, str], tgan)
        self.assertEqual(tgan["proposed_target"], "↑ gaṅ")
        self.assertEqual(tgan["reference_marker_source"], "T")
        self.assertEqual(tgan["reference_marker_target"], "↑")
        self.assertEqual(tgan["base_source_token"], "gan")
        self.assertEqual(tgan["base_proposed_target"], "gaṅ")
        self.assertEqual(tgan["evidence"], "tibetan_script_witness_with_reference_marker")
        self.assertIsNotNone(igan)
        igan = cast(dict[str, str], igan)
        self.assertEqual(igan["proposed_target"], "↑ gaṅ")
        self.assertEqual(igan["reference_marker_source"], "I")
        self.assertEqual(igan["reference_marker_target"], "↑")
        self.assertIsNotNone(slash_gan)
        slash_gan = cast(dict[str, str], slash_gan)
        self.assertEqual(slash_gan["proposed_target"], "↑ gaṅ")
        self.assertEqual(slash_gan["reference_marker_source"], "\\")
        self.assertEqual(slash_gan["reference_marker_target"], "↑")
        self.assertIsNone(
            diag.classify_tibetan_script_ng_token(
                "ldan",
                "ཆུ་དང་ལྡན་པ་ chu dan ldan pa",
            )
        )
        self.assertIsNone(diag.classify_tibetan_script_ng_token("gan", "German gan dan without script"))

    def test_reference_marker_diagnostic_classifies_actual_and_prefixed_markers(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "fake_corrected_full.txt").write_text(
                "གང་ ↑ gan Tgan Igan /gan \\gan Tganı vgl. bka'\n",
                encoding="utf-8",
            )

            rows = diag.build_reference_marker_candidates(run_dir, "fake", self.registry)

        by_token = {row["source_token"]: row for row in rows}
        for token in ["↑", "Tgan", "Igan", "/gan", "\\gan", "Tganı"]:
            with self.subTest(token=token):
                self.assertIn(token, by_token)
        self.assertEqual(by_token["↑"]["candidate_family"], "actual_upward_marker")
        self.assertEqual(by_token["↑"]["suggested_action"], "already_normalized")
        self.assertEqual(by_token["↑"]["attached_token"], "gan")
        self.assertEqual(by_token["Tgan"]["candidate_family"], "ocr_prefix_T_reference_marker_candidate")
        self.assertEqual(by_token["Igan"]["candidate_family"], "ocr_prefix_I_reference_marker_candidate")
        self.assertEqual(by_token["/gan"]["candidate_family"], "ocr_prefix_slash_reference_marker_candidate")
        self.assertEqual(by_token["\\gan"]["candidate_family"], "ocr_prefix_backslash_reference_marker_candidate")
        self.assertEqual(by_token["Tganı"]["normalized_attached_token_candidate"], "gani")
        self.assertEqual(by_token["Tgan"]["suspected_marker_target"], "↑/↓")
        self.assertEqual(by_token["Tgan"]["suspected_direction"], "direction_needs_review")
        self.assertEqual(by_token["Tgan"]["suggested_action"], "exact_review_candidate")

        families = diag.build_reference_marker_token_families(rows)
        self.assertTrue(any(row["suspected_marker_source"] == "/" for row in families))

    def test_reference_marker_controls_are_not_promotion_candidates(self) -> None:
        info = diag.classify_reference_marker_token(
            "International",
            "",
            "International Inhalt der Text",
            None,
            self.registry,
        )

        self.assertIsNone(info)

    def test_initial_i_residual_forms_are_exact_candidates_in_tibetan_context(self) -> None:
        context = "Tib. lta ltas ltar ldan lha lṅa lus lkog lpags bka' la'i"
        examples = {
            "Ita": "lta",
            "Itar": "ltar",
            "Itas": "ltas",
            "Ipags": "lpags",
            "Ius": "lus",
            "Ikog": "lkog",
            "Ina": "lṅa",
            "Idan": "ldan",
        }
        for token, expected in examples.items():
            with self.subTest(token=token):
                info = diag.classify_tibetan_initial_i_token(token, context)
                self.assertIsNotNone(info)
                info = cast(dict[str, str], info)
                self.assertEqual(info["proposed_target"], expected)
                self.assertEqual(info["candidate_family"], "initial_i_to_l")
                self.assertEqual(info["suggested_action"], "exact_promotion_candidate")

    def test_initial_i_residual_scan_is_not_broad_i_rule(self) -> None:
        self.assertIsNone(diag.classify_tibetan_initial_i_token("Ita", "Der Ita und die Lesung ist deutsch."))
        self.assertIsNone(diag.classify_tibetan_initial_i_token("Ita", "Sanskrit sūtra Prajñā Śākyamuni"))
        self.assertIsNone(diag.classify_tibetan_initial_i_token("Ixyz", "Tib. bka' la'i"))

    def test_initial_i_scan_uses_postprocess_token_indexes(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "fake_corrected_full.txt").write_text(
                "(IsKh 2: 230,5); ji Itar 'dam las skyes pa'i ~\n",
                encoding="utf-8",
            )

            rows = diag.build_initial_i_candidates(run_dir, "fake", self.registry)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_token"], "Itar")
        self.assertEqual(rows[0]["token_index"], "6")

    def test_script_ng_scan_uses_postprocess_token_indexes(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "fake_corrected_full.txt").write_text(
                "རང་ (Dagy 12,3) ran\n",
                encoding="utf-8",
            )

            rows = diag.build_script_ng_witness_candidates(run_dir, "fake")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_token"], "ran")
        self.assertEqual(rows[0]["token_index"], "4")

    def test_german_prose_suppresses_tibetan_token_scan(self) -> None:
        candidate = diag.classify_tibetan_token("dnos", "Das ist ein dnos und der Text ist deutsch.")

        self.assertIsNone(candidate)


if __name__ == "__main__":
    unittest.main()

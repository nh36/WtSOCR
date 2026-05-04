import csv
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEM_PATH = ROOT / "scripts" / "postprocess_entry_map.py"
PEM_SPEC = importlib.util.spec_from_file_location("postprocess_entry_map", PEM_PATH)
assert PEM_SPEC is not None and PEM_SPEC.loader is not None
pem = importlib.util.module_from_spec(PEM_SPEC)
sys.modules[PEM_SPEC.name] = pem
PEM_SPEC.loader.exec_module(pem)


class PostprocessRegressionTests(unittest.TestCase):
    def run_postprocess_fixture(
        self,
        merged_text: str,
        *,
        google_vision: bool = False,
        alternate_merged_text: str | None = None,
        alternate_google_vision: bool = False,
        merge_only: bool = False,
    ) -> tuple[dict[str, object], str, list[dict[str, str]]]:
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td, ignore_errors=True)
        root = Path(td)
        merged = root / "fixture_merged.txt"
        alternate_merged = root / "fixture_alternate_merged.txt"
        outdir = root / "out"
        merged.write_text(merged_text, encoding="utf-8")
        if alternate_merged_text is not None:
            alternate_merged.write_text(alternate_merged_text, encoding="utf-8")
        outdir.mkdir(parents=True, exist_ok=True)

        result = pem.run_one(
            merged=merged,
            audit=None,
            outdir=outdir,
            label="fixture",
            trusted_min_freq=2,
            discover_max_edit=2,
            discover_max_rare_freq=3,
            google_vision=google_vision,
            alternate_merged=alternate_merged if alternate_merged_text is not None else None,
            alternate_google_vision=alternate_google_vision,
            merge_only=merge_only,
        )
        corrected = Path(result["corrected_full"]).read_text(encoding="utf-8")
        with Path(result["changes_tsv"]).open(newline="", encoding="utf-8") as f:
            changes = list(csv.DictReader(f, delimiter="\t"))
        return result, corrected, changes

    def test_google_vision_loc_confusables_tibetan_context(self) -> None:
        merged_text = "བྱང་ byaň\nབཟང་ bzań po žes šes rab\n"
        result, corrected, changes = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("byaṅ", corrected)
        self.assertIn("bzaṅ po źes śes rab", corrected)
        self.assertEqual(result["google_vision_rewrites"], 4)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("byaň", "byaṅ", "google_vision_loc_confusable"), reasons)
        self.assertIn(("bzań", "bzaṅ", "google_vision_loc_confusable"), reasons)
        self.assertIn(("žes", "źes", "google_vision_loc_confusable"), reasons)
        self.assertIn(("šes", "śes", "google_vision_loc_confusable"), reasons)

    def test_google_vision_loc_confusables_protects_slavic_bibliography(self) -> None:
        merged_text = "བྱང་ byaň\nŠčerbackoj 1904: Nyāyabindu.\n"
        _, corrected, _ = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("byaṅ", corrected)
        self.assertIn("Ščerbackoj", corrected)
        self.assertNotIn("Śčerbackoj", corrected)

    def test_google_vision_loc_confusables_raw_vision_line_without_entry_context(self) -> None:
        merged_text = "Kah thog rig 'dzin Tshe dbaň nor bu'i žabs kyi rnam thar\n"
        result, corrected, changes = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("dbaṅ", corrected)
        self.assertIn("źabs", corrected)
        self.assertEqual(result["google_vision_rewrites"], 2)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("dbaň", "dbaṅ", "google_vision_loc_confusable"), reasons)
        self.assertIn(("žabs", "źabs", "google_vision_loc_confusable"), reasons)

    def test_google_vision_page_markers_are_normalized(self) -> None:
        merged_text = (
            "=== page 001 ===\n"
            "བྱང་ byaň\n"
            "=== page 002 ===\n"
            "གསང་ gsań\n"
        )
        result, corrected, _ = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("\f", corrected)
        self.assertIn("byaṅ", corrected)
        self.assertIn("gsaṅ", corrected)
        self.assertEqual(result["google_vision_rewrites"], 2)

    def test_google_vision_nasal_confusables_keep_palatal_nasal_clusters(self) -> None:
        merged_text = "mňam pa sniň po gňis mňon dňul\n"
        result, corrected, _ = self.run_postprocess_fixture(merged_text, google_vision=True)

        self.assertIn("mñam pa sñiṅ po gñis mṅon dṅul", corrected)
        self.assertEqual(result["google_vision_rewrites"], 5)

    def test_alternate_witness_adopts_clean_translit_token(self) -> None:
        merged_text = "ཞེས་ žes\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(newline="", encoding="utf-8") as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "žes")
        self.assertEqual(adoptions[0]["alternate_token"], "źes")
        self.assertEqual(adoptions[0]["reason"], "alternate_witness_strict_translit")

    def test_alternate_witness_logs_unresolved_unsafe_disagreement(self) -> None:
        merged_text = "ཀོང་ koṅ po\n"
        alternate_merged_text = "=== page 001 ===\nཀོང་ kuṅ po\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["base_token"], "koṅ")
        self.assertEqual(unresolved[0]["alternate_token"], "kuṅ")
        self.assertEqual(unresolved[0]["reason"], "unsafe_token_disagreement")

    def test_alternate_witness_adopts_google_loc_fricative_upgrade(self) -> None:
        merged_text = "ཞེས་ zes\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

        with Path(result["alternate_witness_adoptions_tsv"]).open(newline="", encoding="utf-8") as f:
            adoptions = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(adoptions), 1)
        self.assertEqual(adoptions[0]["base_token"], "zes")
        self.assertEqual(adoptions[0]["alternate_token"], "źes")
        self.assertEqual(
            adoptions[0]["reason"],
            "alternate_witness_google_loc_fricative_upgrade",
        )

    def test_alternate_witness_does_not_adopt_clean_nasal_disagreement(self) -> None:
        merged_text = "ཀོང་ kon po\n"
        alternate_merged_text = "=== page 001 ===\nཀོང་ koň po\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("kon po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["base_token"], "kon")
        self.assertEqual(unresolved[0]["alternate_token"], "koṅ")
        self.assertEqual(unresolved[0]["reason"], "unsafe_token_disagreement")

    def test_merge_only_uses_cleaned_alternate_witness_without_downstream_cleanup(self) -> None:
        merged_text = "\f1\nཞེས་ žes\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, rows = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
            merge_only=True,
        )

        self.assertTrue(result["merge_only"])
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["trusted_lexicon_size"], 0)
        self.assertEqual(result["discovered_patterns"], 0)
        self.assertEqual(result["citation_name_changes"], 0)
        self.assertEqual(result["sanskrit_changes"], 0)
        self.assertIn("ཞེས་ źes", corrected)
        self.assertEqual(rows, [])

    def test_alternate_witness_ignores_form_feed_page_number_line(self) -> None:
        merged_text = "\f1\nཞེས་ žes\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, rows = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("ཞེས་ źes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)
        self.assertEqual(rows, [])

    def test_alternate_witness_aligns_collapsed_blank_lines(self) -> None:
        merged_text = "ཞེས་ žes\n\nཀོང་ koṅ po\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\nཀོང་ koṅ po\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes", corrected)
        self.assertIn("\n\nཀོང་ koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_scans_forward_to_next_alignable_page(self) -> None:
        merged_text = "ཞེས་ žes\n\fཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "dummy page\n"
            "=== page 002 ===\n"
            "ཞེས་ žes\n"
            "=== page 003 ===\n"
            "ཀོང་ koṅ po\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes", corrected)
        self.assertIn("\fཀོང་ koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_scans_forward_across_rewrapped_page(self) -> None:
        merged_text = "ཞེས་ žes koṅ po\n\fཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "dummy page\n"
            "=== page 002 ===\n"
            "ཞེས་ žes\n"
            "koṅ po\n"
            "=== page 003 ===\n"
            "ཀོང་ koṅ po\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes koṅ po", corrected)
        self.assertIn("\fཀོང་ koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_rejects_page_with_only_one_compatible_line(self) -> None:
        merged_text = "ཞེས་ žes\nཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཞེས་ žes\n"
            "completely unrelated witness text\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("žes", corrected)
        self.assertIn("koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["reason"], "unalignable_page_content")

    def test_alternate_witness_aligns_normalized_non_token_fragments(self) -> None:
        merged_text = "ཞེས་ žes (Mvy 1)\nཀོང་ koṅ po\n"
        alternate_merged_text = (
            "=== page 001 ===\n"
            "ཞེས་ žes(MVY 1)\n"
            "ཀོང་ koň po\n"
        )

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("źes (Mvy 1)", corrected)
        self.assertIn("koṅ po", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 1)
        self.assertEqual(result["alternate_witness_unresolved"], 0)

    def test_alternate_witness_rejects_nonempty_line_loss(self) -> None:
        merged_text = "ཞེས་ žes\nཀོང་ koṅ po\n"
        alternate_merged_text = "=== page 001 ===\nཞེས་ žes\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("žes", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["reason"], "nonempty_line_count_mismatch")
        self.assertEqual(unresolved[0]["base_key"], "2")
        self.assertEqual(unresolved[0]["alternate_key"], "1")

    def test_alternate_witness_does_not_adopt_loc_loss(self) -> None:
        merged_text = "གཉིས་ gñis\n"
        alternate_merged_text = "=== page 001 ===\nགཉིས་ gnis\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("gñis", corrected)
        self.assertNotIn("gnis", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["base_token"], "gñis")
        self.assertEqual(unresolved[0]["alternate_token"], "gnis")
        self.assertEqual(unresolved[0]["reason"], "unsafe_token_disagreement")

    def test_alternate_witness_does_not_adopt_loc_loss_in_gner(self) -> None:
        merged_text = "གཉེར་ gñer\n"
        alternate_merged_text = "=== page 001 ===\nགཉེར་ gner\n"

        result, corrected, _ = self.run_postprocess_fixture(
            merged_text,
            alternate_merged_text=alternate_merged_text,
            alternate_google_vision=True,
        )

        self.assertIn("gñer", corrected)
        self.assertNotIn("gner", corrected)
        self.assertEqual(result["alternate_witness_adoptions"], 0)
        self.assertEqual(result["alternate_witness_unresolved"], 1)

        with Path(result["alternate_witness_unresolved_tsv"]).open(newline="", encoding="utf-8") as f:
            unresolved = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["base_token"], "gñer")
        self.assertEqual(unresolved[0]["alternate_token"], "gner")
        self.assertEqual(unresolved[0]["reason"], "unsafe_token_disagreement")

    def test_high_risk_token_regressions(self) -> None:
        merged_text = (
            "ཀོང་ $in po\n"
            "dgra-Iba-Gottheit dPal-Idan g$egs $in tu dga'o dpe'i gañdza\n"
            "ཁོ་ kho\n"
        )
        result, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("śin tu", corrected)
        self.assertNotIn("śiṅ tu", corrected)
        self.assertIn("dgra-lba-Gottheit", corrected)
        self.assertIn("dPal-ldan", corrected)
        self.assertIn("gśegs", corrected)
        self.assertIn("dga'o", corrected)
        self.assertIn("dpe'i", corrected)
        self.assertIn("gañdza", corrected)

        reasons = {(row["from_token"].lower(), row["to_token"].lower(), row["reason"]) for row in changes}
        self.assertIn(("$in", "śin", "explicit_user_allowlist_in_tu"), reasons)
        self.assertIn(("dgra-iba-gottheit", "dgra-lba-gottheit", "explicit_user_allowlist"), reasons)
        self.assertIn(("dpal-idan", "dpal-ldan", "explicit_user_allowlist"), reasons)
        self.assertIn(("g$egs", "gśegs", "explicit_user_allowlist"), reasons)
        self.assertEqual(result["tier_b_suggestions"], 0)

    def test_hard_guard_blocks_particle_suffix_drop(self) -> None:
        self.assertEqual(
            pem.rewrite_hard_guard_block_reason("dga'o", "dga", "test_reason", stage="entry"),
            "particle_suffix_drop",
        )
        self.assertEqual(
            pem.rewrite_hard_guard_block_reason("dpe'i", "dpe", "test_reason", stage="entry"),
            "particle_suffix_drop",
        )

    def test_sigla_registry_load_smoke(self) -> None:
        self.assertTrue(pem.SIGLA_REGISTRY_PATH.exists())
        canonical, confusable = pem.load_sigla_registry(pem.SIGLA_REGISTRY_PATH)
        self.assertIn("Liś", canonical)
        self.assertEqual(confusable.get("lís"), "Liś")

    def test_citation_sigla_confusables_normalized(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(NOBEL 1950:12) L$dz L$dz-K Vi$T Vi$ST Vis$T Li$ Lis$ Y$' Lis Lsdz Lsdz-K Lsdz-R\n"
            "vgl. (NOBEL 1951:13) L$dz Vi$T Vis$T Y$ Lis Lsdz\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Lśdz", corrected)
        self.assertIn("Lśdz-K", corrected)
        self.assertIn("Lśdz-R", corrected)
        self.assertIn("VisT", corrected)
        self.assertIn("Liś", corrected)
        self.assertIn("Ys'", corrected)
        self.assertIn("Ys", corrected)
        self.assertNotIn("L$dz", corrected)
        self.assertNotIn("Vi$T", corrected)
        self.assertNotIn("Vi$ST", corrected)
        self.assertNotIn("Vis$T", corrected)
        self.assertNotIn("Li$", corrected)
        self.assertNotIn("Lis$", corrected)
        self.assertNotIn("Y$", corrected)
        self.assertNotIn(" Lis ", corrected)
        self.assertNotIn(" Lsdz", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("L$dz", "Lśdz", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("L$dz-K", "Lśdz-K", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vi$T", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vi$ST", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vis$T", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Li$", "Liś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lis$", "Liś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Y$", "Ys", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lis", "Liś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lsdz", "Lśdz", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lsdz-K", "Lśdz-K", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lsdz-R", "Lśdz-R", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_y_dollar_cue_without_year_or_siglum_word_boundary(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "sowie Durst bei Austrocknung“ (Y$ 96c).\n"
            "die Weisen als Wirkungen der Galle“ (Y$\n"
            "973); rna mchog 977/$ po'i ltag pa\n"
            "Gewalt gebracht“ (Li$ 17,10; KlonD 739,6;\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("(Ys 96c).", corrected)
        self.assertIn("(Ys", corrected)
        self.assertIn("(Liś 17,10; KlonD 739,6;", corrected)
        self.assertNotIn("Y$", corrected)
        self.assertNotIn("Li$", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Y$", "Ys", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Li$", "Liś", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_context_gate_keeps_lexical_lis(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "NOBEL 1950 lorem ipsum dolor sit amet consectetur adipisicing elit Lis.\n"
            "vgl. (Lis 30,2) und sonstiges.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("elit Lis.", corrected)
        self.assertIn("(Liś 30,2)", corrected)

        lis_siglum_changes = [
            row
            for row in changes
            if row["from_token"] == "Lis"
            and row["to_token"] == "Liś"
            and row["reason"] == "citation_siglum_confusable_map"
        ]
        self.assertEqual(len(lis_siglum_changes), 1)

    def test_citation_sigla_extended_safe_normalization(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(P$ 7c) (Bu-$z 51,3) (Vi$ 67b) (Vis$ 6b) ($ambh 5b6) ($PS 38) "
            "(RoIN$ 35,1) (In$ 29) (G$ 93a) (G$-H 481) (G$S-H 74a) (L1$ 30,2) (1.$dz 69,2) "
            "(ISK 5a) (1ISK 6b)\n"
            "(ViST 228,30) (VisST 142,4) (VIST 158,23) (VIiST 210,6) (YS 80d) (GS-H 60d)\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("(Ps 7c)", corrected)
        self.assertIn("(Bu-Sz 51,3)", corrected)
        self.assertIn("(Vis 67b)", corrected)
        self.assertIn("(Vis 6b)", corrected)
        self.assertIn("(Śambh 5b6)", corrected)
        self.assertIn("(SPS 38)", corrected)
        self.assertIn("(RoINS 35,1)", corrected)
        self.assertIn("(Ins 29)", corrected)
        self.assertIn("(Gs 93a)", corrected)
        self.assertIn("(Gs-H 481)", corrected)
        self.assertIn("(Gs-H 74a)", corrected)
        self.assertIn("(VisT 228,30)", corrected)
        self.assertIn("(VisT 142,4)", corrected)
        self.assertIn("(VisT 158,23)", corrected)
        self.assertIn("(VisT 210,6)", corrected)
        self.assertIn("(Ys 80d)", corrected)
        self.assertIn("(Gs-H 60d)", corrected)
        self.assertIn("(Liś 30,2)", corrected)
        self.assertIn("(1.śdz 69,2)", corrected)
        self.assertIn("(1SK 5a)", corrected)
        self.assertIn("(1SK 6b)", corrected)

        self.assertNotIn("(P$ 7c)", corrected)
        self.assertNotIn("(Bu-$z 51,3)", corrected)
        self.assertNotIn("(Vi$ 67b)", corrected)
        self.assertNotIn("(Vis$ 6b)", corrected)
        self.assertNotIn("($ambh 5b6)", corrected)
        self.assertNotIn("($PS 38)", corrected)
        self.assertNotIn("(RoIN$ 35,1)", corrected)
        self.assertNotIn("(In$ 29)", corrected)
        self.assertNotIn("(G$ 93a)", corrected)
        self.assertNotIn("(G$-H 481)", corrected)
        self.assertNotIn("(G$S-H 74a)", corrected)
        self.assertNotIn("(ViST 228,30)", corrected)
        self.assertNotIn("(VisST 142,4)", corrected)
        self.assertNotIn("(VIST 158,23)", corrected)
        self.assertNotIn("(VIiST 210,6)", corrected)
        self.assertNotIn("(YS 80d)", corrected)
        self.assertNotIn("(GS-H 60d)", corrected)
        self.assertNotIn("(L1$ 30,2)", corrected)
        self.assertNotIn("(1.$dz 69,2)", corrected)
        self.assertNotIn("(ISK 5a)", corrected)
        self.assertNotIn("(1ISK 6b)", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("P$", "Ps", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Bu-$z", "Bu-Sz", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vi$", "Vis", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vis$", "Vis", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("$ambh", "Śambh", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("$PS", "SPS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("RoIN$", "RoINS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("In$", "Ins", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("G$", "Gs", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("G$-H", "Gs-H", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("G$S-H", "Gs-H", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("ViST", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("VisST", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("VIST", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("VIiST", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("YS", "Ys", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("GS-H", "Gs-H", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("L1$", "Liś", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("ISK", "1SK", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("1ISK", "1SK", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_standalone_and_split_lines(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "$Sambh\n"
            "RoIN$\n"
            "vgl. „x“ (P$ Kolophon);\n"
            "„y“ (Bu-$2\n"
            "22,9); z\n"
            "„z“ (X$ 68d);\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Śambh", corrected)
        self.assertIn("RoINS", corrected)
        self.assertIn("(Ps Kolophon)", corrected)
        self.assertIn("(Bu-Sz", corrected)
        self.assertIn("(Xs 68d)", corrected)
        self.assertNotIn("$Sambh", corrected)
        self.assertNotIn("RoIN$", corrected)
        self.assertNotIn("(P$ Kolophon)", corrected)
        self.assertNotIn("(Bu-$2", corrected)
        self.assertNotIn("(X$ 68d)", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("$Sambh", "Śambh", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("RoIN$", "RoINS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("P$", "Ps", "citation_siglum_confusable_map"), reasons)
        self.assertTrue(
            any(
                from_tok in {"Bu-$2", "Bu-$"}
                and to_tok == "Bu-Sz"
                and reason == "citation_siglum_confusable_map"
                for from_tok, to_tok, reason in reasons
            )
        )
        self.assertIn(("X$", "Xs", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_doll_roins_and_bhullg_guardrails(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Doll\n"
            "RoINs\n"
            "vgl. (Doll 12,4) und (RoINs 7,1) und (RoINSs 21,9) und (BhuLlg 33,2).\n"
            "Eine Puppe heißt Doll im Englischen.\n"
            "Bhulg und BhuLg bleiben.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("\nDol1\n", corrected)
        self.assertIn("\nRoINS\n", corrected)
        self.assertIn("(Dol1 12,4)", corrected)
        self.assertIn("(RoINS 7,1)", corrected)
        self.assertIn("(RoINS 21,9)", corrected)
        self.assertIn("(BhuLg 33,2)", corrected)
        self.assertIn("Eine Puppe heißt Doll im Englischen.", corrected)
        self.assertIn("Bhulg und BhuLg bleiben.", corrected)
        self.assertNotIn("(Doll 12,4)", corrected)
        self.assertNotIn("(RoINs 7,1)", corrected)
        self.assertNotIn("(RoINSs 21,9)", corrected)
        self.assertNotIn("(BhuLlg 33,2)", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Doll", "Dol1", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("RoINs", "RoINS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("RoINSs", "RoINS", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("BhuLlg", "BhuLg", "citation_siglum_confusable_map"), reasons)

    def test_sigla_standalone_allowlist_applies_on_base_citation_lines(self) -> None:
        self.assertTrue(
            pem.token_has_siglum_context(
                "Doll",
                "Doll",
                0,
                4,
                line_is_base_citation=True,
                line_siglum_context_cue=False,
                line_siglum_candidate_count=1,
            )
        )
        self.assertTrue(
            pem.token_has_siglum_context(
                "RoINs",
                "RoINs",
                0,
                5,
                line_is_base_citation=True,
                line_siglum_context_cue=False,
                line_siglum_candidate_count=1,
            )
        )
        self.assertFalse(
            pem.token_has_siglum_context(
                "Haus",
                "Haus",
                0,
                4,
                line_is_base_citation=True,
                line_siglum_context_cue=False,
                line_siglum_candidate_count=1,
            )
        )

    def test_citation_sigla_allowlist_applies_in_frontmatter_entry_zero(self) -> None:
        merged_text = (
            "Doll\n"
            "RoINs\n"
            "SCHMIDT 1841 (Tibetisch-Deutsches Wörterbuch).\n"
        )
        _, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("\nDol1\n", f"\n{corrected}")
        self.assertIn("\nRoINS\n", f"\n{corrected}")
        self.assertNotIn("\nDoll\n", f"\n{corrected}")
        self.assertNotIn("\nRoINs\n", f"\n{corrected}")

    def test_citation_sigla_allowlist_open_paren_wrap_context(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "vgl. (RoINs 7,1).\n"
            "weitere Stelle (Doll\n"
            "24,21) im Kontext.\n"
        )
        _, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("(RoINS 7,1).", corrected)
        self.assertIn("(Dol1\n24,21)", corrected)
        self.assertNotIn("(RoINs 7,1).", corrected)
        self.assertNotIn("(Doll\n24,21)", corrected)

    def test_citation_sigla_allowlist_formfeed_wrap_context(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "weitere Stelle (Doll\f"
            "24,21) im Kontext.\n"
        )
        _, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("(Dol1\f24,21)", corrected)
        self.assertNotIn("(Doll\f24,21)", corrected)

    def test_citation_sigla_allowlist_intro_list_context(self) -> None:
        merged_text = (
            "Die verwendeten Abkürzungen sind historisch gewachsen.\n"
            "Texte in Sammelbänden wurden ebenfalls durchnumeriert "
            "(Bb33, Bb45, Doll, Dol3 usw.).\n"
            "Eine Puppe heißt Doll im Englischen.\n"
        )
        _, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("(Bb33, Bb45, Dol1, Dol3 usw.)", corrected)
        self.assertIn("Eine Puppe heißt Doll im Englischen.", corrected)
        self.assertNotIn("(Bb33, Bb45, Doll, Dol3 usw.)", corrected)

    def test_german_dotless_i_extended_safe_map_and_numeric(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Eın Artıkel ıst 111 den Fällen und 1111 Oktober publızıert.\n"
            "Dıes dıeserlei dıejenigen Wırkung Stıftung Bıld Schrıft Schrıftsprache Tıbetisch Tıbetologen.\n"
            "lexıkographisch und lexıkalisch in der Kommunıikation der Verwaltıng.\n"
            "Bıographie und bıographisch; nıeder, nıederlassen, vernıchten, gelıngen.\n"
            "Seı beı der Basıs und Iranıstik beschleunıgen.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Ein Artikel ist in den Fällen und im Oktober publiziert.", corrected)
        self.assertIn(
            "Dies dieserlei diejenigen Wirkung Stiftung Bild Schrift Schriftsprache Tibetisch Tibetologen.",
            corrected,
        )
        self.assertIn("lexikographisch und lexikalisch in der Kommunikation der Verwaltung.", corrected)
        self.assertIn("Biographie und biographisch; nieder, niederlassen, vernichten, gelingen.", corrected)
        self.assertIn("Sei bei der Basis und Iranistik beschleunigen.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Eın", "Ein", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("Artıkel", "Artikel", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("111", "in", "german_numeric_function_word_confusion"), reasons)
        self.assertIn(("1111", "im", "german_numeric_function_word_confusion"), reasons)
        self.assertIn(("publızıert", "publiziert", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("Basıs", "Basis", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("Iranıstik", "Iranistik", "german_dotless_i_safe_map"), reasons)

    def test_citation_name_safe_map(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(NOBEL 1950:12) Tromas Wyrıe Pangiunc Pangiung Stem Kvzrne Engliish oftheIndo-Aryan "
            "VoceL RicHarpson JAscake.\n"
            "Das Stem bleibt in der Prosa unverändert.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("(NOBEL 1950:12) Thomas Wylie Panglung Panglung Stein Kværne English of the Indo-Aryan", corrected)
        self.assertIn("VoceL RicHarpson JAscake.", corrected)
        self.assertIn("Das Stem bleibt in der Prosa unverändert.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Tromas", "Thomas", "citation_name_safe_map"), reasons)
        self.assertIn(("Wyrıe", "Wylie", "citation_name_safe_map"), reasons)
        self.assertIn(("Pangiunc", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("Pangiung", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("Stem", "Stein", "citation_name_safe_map"), reasons)
        self.assertIn(("Kvzrne", "Kværne", "citation_name_safe_map"), reasons)

    def test_citation_safe_map_extended_bibliography_cleanup(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(SCHMIDT 1902:7) UesachH UzsachH Pansiung Pansıung PangLung Cürpers Denwoop Schwirger Granmatik "
            "Hindn Into SreinGass ZongrTse Dierz manuseript Vollkommenbeiten Ihe Iwo accompaniedbya.\n"
            "(SCHMIDT 1902:8) Pangıunc.\n"
            "(STEIN 1961:4) P rsian-English vice versä.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "(SCHMIDT 1902:7) Uebach Uebach Panglung Panglung Panglung Cüppers Denwood Schwieger Grammatik "
            "Hindu into Steingass Zongtse Dietz manuscript Vollkommenheiten The Two accompanied by a.",
            corrected,
        )
        self.assertIn("(SCHMIDT 1902:8) Panglung.", corrected)
        self.assertIn("(STEIN 1961:4) Persian-English vice versa.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("UesachH", "Uebach", "citation_name_safe_map"), reasons)
        self.assertIn(("UzsachH", "Uebach", "citation_name_safe_map"), reasons)
        self.assertIn(("Pansiung", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("Pansıung", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("Pangıunc", "Panglung", "citation_name_safe_map"), reasons)
        self.assertIn(("PangLung", "Panglung", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("SreinGass", "Steingass", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("Into", "into", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("Ihe", "The", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("Iwo", "Two", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("accompaniedbya", "accompanied by a", "citation_english_spacing_loss_map"), reasons)
        self.assertIn(("P rsian-English", "Persian-English", "citation_phrase_safe_map"), reasons)
        self.assertIn(("vice versä", "vice versa", "citation_phrase_safe_map"), reasons)

    def test_bibliography_author_year_and_continuation_lines_are_citation_like(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Schwirger, Peter 20092. Handbuch zur Granmatik der klassischen tibetischen Schrift-\n"
            "for the conversion of Hindu and Muhammadan Into A.D. dates, and vice versä.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "Schwieger, Peter 20092. Handbuch zur Grammatik der klassischen tibetischen Schrift-",
            corrected,
        )
        self.assertIn(
            "for the conversion of Hindu and Muhammadan into A.D. dates, and vice versa.",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Schwirger", "Schwieger", "citation_name_safe_map"), reasons)
        self.assertIn(("Granmatik", "Grammatik", "citation_name_safe_map"), reasons)
        self.assertIn(("Into", "into", "citation_token_exact_safe_map"), reasons)
        self.assertIn(("vice versä", "vice versa", "citation_phrase_safe_map"), reasons)

    def test_bibliography_continuations_and_gloss_lines_get_narrow_context_fixes(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "3. ıch, für skt. abam.\n"
            "1. sıch niederlassen.\n"
            "geraten, sıch untereinander nicht einig wer-\n"
            "will ıch zuerst vernichten (Mil 66,9).\n"
            "tig, ıch diente ihr (Bca 7.52b).\n"
            "Säkya-mchog-ldan. Reproduced from the unique manuseript prepared in the library.\n"
            "tische Text unter Mitarbeit von Siglinde Dierz hg. v. Champa Thupten ZongrTse.\n"
            "— /Pansiung, Lokesh Chandra 1982.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("3. ich, für skt. abam.", corrected)
        self.assertIn("1. sich niederlassen.", corrected)
        self.assertIn("geraten, sich untereinander nicht einig wer-", corrected)
        self.assertIn("will ich zuerst vernichten (Mil 66,9).", corrected)
        self.assertIn("tig, ich diente ihr (Bca 7.52b).", corrected)
        self.assertIn("Reproduced from the unique manuscript prepared in the library.", corrected)
        self.assertIn("Siglinde Dietz hg. v. Champa Thupten Zongtse.", corrected)
        self.assertIn("— /Panglung, Lokesh Chandra 1982.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("ıch", "ich", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("sıch", "sich", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("manuseript", "manuscript", "citation_name_safe_map"), reasons)
        self.assertIn(("Dierz", "Dietz", "citation_name_safe_map"), reasons)
        self.assertIn(("ZongrTse", "Zongtse", "citation_name_safe_map"), reasons)
        self.assertIn(("Pansiung", "Panglung", "citation_name_safe_map"), reasons)

    def test_new_exact_german_function_word_and_dotless_i_rewrites(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Wir sahen 6111 Blättern und €111 Beispiel, nicht aber ©111 42.\n"
            "cine cinem cinen ciner cines seı Eın eın ıst.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Wir sahen ein Blättern und ein Beispiel, nicht aber ©111 42.", corrected)
        self.assertIn("eine einem einen einer eines sei Ein ein ist.", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("6111", "ein", "german_numeric_function_word_confusion"), reasons)
        self.assertIn(("€111", "ein", "german_numeric_function_word_confusion"), reasons)
        self.assertNotIn(("©111", "ein", "german_numeric_function_word_confusion"), reasons)
        self.assertIn(("cine", "eine", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("cinem", "einem", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("cinen", "einen", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("ciner", "einer", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("cines", "eines", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("seı", "sei", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("Eın", "Ein", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("eın", "ein", "german_dotless_i_safe_map"), reasons)
        self.assertIn(("ıst", "ist", "german_dotless_i_safe_map"), reasons)

    def test_new_exact_tibetan_allowlist_rewrites(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "rmams breyud broyud broyad bsnal biin giien giier bsiien siian giis giiis griis miiam yiin fiid "
            "kyı kyıs gyı gyıs yın cıg gcıg zıg sıg dkyıl kyanı yanı byanı gsarı snanı sarıs garı Igarı\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "rnams brgyud brgyud brgyad bsṅal bźin gñen gñer bsñen sñan gñis gñis gñis mñam yin ñid "
            "kyi kyis gyi gyis yin cig gcig zig sig dkyil kyaṅ yaṅ byaṅ gsaṅ snaṅ saṅs gaṅ lgaṅ",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("rmams", "rnams", "explicit_user_allowlist"), reasons)
        self.assertIn(("breyud", "brgyud", "explicit_user_allowlist"), reasons)
        self.assertIn(("broyud", "brgyud", "explicit_user_allowlist"), reasons)
        self.assertIn(("broyad", "brgyad", "explicit_user_allowlist"), reasons)
        self.assertIn(("bsnal", "bsṅal", "explicit_user_allowlist"), reasons)
        self.assertIn(("biin", "bźin", "explicit_user_allowlist"), reasons)
        self.assertIn(("giien", "gñen", "explicit_user_allowlist"), reasons)
        self.assertIn(("giier", "gñer", "explicit_user_allowlist"), reasons)
        self.assertIn(("bsiien", "bsñen", "explicit_user_allowlist"), reasons)
        self.assertIn(("siian", "sñan", "explicit_user_allowlist"), reasons)
        self.assertIn(("giis", "gñis", "explicit_user_allowlist"), reasons)
        self.assertIn(("giiis", "gñis", "explicit_user_allowlist"), reasons)
        self.assertIn(("griis", "gñis", "explicit_user_allowlist"), reasons)
        self.assertIn(("miiam", "mñam", "explicit_user_allowlist"), reasons)
        self.assertIn(("yiin", "yin", "explicit_user_allowlist"), reasons)
        self.assertIn(("fiid", "ñid", "explicit_user_allowlist"), reasons)
        self.assertIn(("kyı", "kyi", "explicit_user_allowlist"), reasons)
        self.assertIn(("kyıs", "kyis", "explicit_user_allowlist"), reasons)
        self.assertIn(("gyı", "gyi", "explicit_user_allowlist"), reasons)
        self.assertIn(("gyıs", "gyis", "explicit_user_allowlist"), reasons)
        self.assertIn(("yın", "yin", "explicit_user_allowlist"), reasons)
        self.assertIn(("cıg", "cig", "explicit_user_allowlist"), reasons)
        self.assertIn(("gcıg", "gcig", "explicit_user_allowlist"), reasons)
        self.assertIn(("zıg", "zig", "explicit_user_allowlist"), reasons)
        self.assertIn(("sıg", "sig", "explicit_user_allowlist"), reasons)
        self.assertIn(("dkyıl", "dkyil", "explicit_user_allowlist"), reasons)
        self.assertIn(("kyanı", "kyaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("yanı", "yaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("byanı", "byaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("gsarı", "gsaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("snanı", "snaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("sarıs", "saṅs", "explicit_user_allowlist"), reasons)
        self.assertIn(("garı", "gaṅ", "explicit_user_allowlist"), reasons)
        self.assertIn(("Igarı", "lgaṅ", "explicit_user_allowlist"), reasons)

    def test_new_tibetan_allowlist_does_not_spill_into_plain_german_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "Ein Druckfehler wie kyanı oder yani oder zıg oder snanı oder garı oder Igarı soll hier nicht automatisch korrigiert werden.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "Ein Druckfehler wie kyanı oder yani oder zıg oder snanı oder garı oder Igarı soll hier nicht automatisch korrigiert werden.",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(("kyanı", "kyaṅ", "explicit_user_allowlist"), reasons)
        self.assertNotIn(("zıg", "zig", "explicit_user_allowlist"), reasons)
        self.assertNotIn(("snanı", "snaṅ", "explicit_user_allowlist"), reasons)
        self.assertNotIn(("garı", "gaṅ", "explicit_user_allowlist"), reasons)
        self.assertNotIn(("Igarı", "lgaṅ", "explicit_user_allowlist"), reasons)

    def test_tibetan_phrase_allowlist_rewrites_tshul_khrims(self) -> None:
        merged_text = (
            "ཚུལ་ཁྲིམས་ tshul khrims\n"
            "tsbul kbrims rnam par dag pa\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("tshul khrims rnam par dag pa", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("tsbul kbrims", "tshul khrims", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_does_not_rewrite_orphan_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "Ein Druckfehler tsbul kbrims bleibt hier unverändert.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("tsbul kbrims", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(
            ("tsbul kbrims", "tshul khrims", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_rewrites_dang_ldan_pa(self) -> None:
        merged_text = (
            "དང་ལྡན་པ་ daṅ ldan pa\n"
            "dan ldan pa yin no\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("daṅ ldan pa yin no", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("dan ldan pa", "daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_does_not_rewrite_dang_ldan_pa_in_plain_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "Ein Druckfehler dan ldan pa bleibt hier unverändert.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("dan ldan pa", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(
            ("dan ldan pa", "daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_dang_phrase_override_rewrites_curated_phrase(self) -> None:
        merged_text = (
            "ཀུན་སྣང་དང་པ་ཅན་ kun snan daṅ pa can\n"
            "ཀུན་སྣང་དང་པ་ཅན་ kun snan dan pa can, auch kun\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("kun snan daṅ pa can, auch kun", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            (
                "ཀུན་སྣང་དང་པ་ཅན་ kun snan dan pa can, auch kun",
                "ཀུན་སྣང་དང་པ་ཅན་ kun snan daṅ pa can, auch kun",
                "tibetan_dang_phrase_override",
            ),
            reasons,
        )

    def test_tibetan_dang_phrase_override_does_not_rewrite_plain_prose(self) -> None:
        merged_text = (
            "Dies ist rein deutsche Prosa ohne tibetischen Kopf.\n"
            "kun snan dan pa can, auch kun\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("kun snan dan pa can, auch kun", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(
            (
                "ཀུན་སྣང་དང་པ་ཅན་ kun snan dan pa can, auch kun",
                "ཀུན་སྣང་དང་པ་ཅན་ kun snan daṅ pa can, auch kun",
                "tibetan_dang_phrase_override",
            ),
            reasons,
        )

    def test_boundary_safe_tibetan_l_cluster_and_bzi_rewrites(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Ita Iha Ihan Iho Itos bii bii' bii’ bii'an bii’an bii'o bii’o bii'i bii’i fooItaBar\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "lta lha lhan lho ltos bźi bźi' bźi’ bźi'an bźi’an bźi'o bźi’o bźi'i bźi’i fooItaBar",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Ita", "lta", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("Iha", "lha", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("Ihan", "lhan", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("Iho", "lho", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("Itos", "ltos", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii", "bźi", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii'", "bźi'", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii’", "bźi’", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii'an", "bźi'an", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii’an", "bźi’an", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii'o", "bźi'o", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii’o", "bźi’o", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii'i", "bźi'i", "explicit_case_sensitive_allowlist"), reasons)
        self.assertIn(("bii’i", "bźi’i", "explicit_case_sensitive_allowlist"), reasons)

    def test_hyphenated_i_l_fixes_keep_loc_transliteration(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Brag-Iha dGra-Iha'i Bkra-śis-Ihun-po foo-IhaBar\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Brag-lha dGra-lha'i Bkra-śis-lhun-po foo-IhaBar", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Brag-Iha", "Brag-lha", "confusable_hyphenated_I_to_l_translit"), reasons)
        self.assertIn(("dGra-Iha'i", "dGra-lha'i", "confusable_hyphenated_I_to_l_translit"), reasons)
        self.assertIn(("Bkra-śis-Ihun-po", "Bkra-śis-lhun-po", "confusable_hyphenated_I_to_l_translit"), reasons)
        self.assertNotIn(("fooItaBar", "fooltaBar", "explicit_case_sensitive_allowlist"), reasons)

    def test_tibetan_dang_witness_rewrites_latin_dan(self) -> None:
        merged_text = (
            "ཆུ་དང་ལྡན་པ་ chu dan ldan pa\n"
            "དང་པོ་ dan po\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("ཆུ་དང་ལྡན་པ་ chu daṅ ldan pa", corrected)
        self.assertIn("དང་པོ་ daṅ po", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("dan ldan pa", "daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_rewrites_curated_x_dan_ldan_pa_forms(self) -> None:
        merged_text = (
            "ཆོས་ chos\n"
            "skal ba dan ldan pa rnams stobs dan ldan pas chos dan ldan pa'i "
            "dpal dbaṅ dan ldan pa yi stobs dan ldan pa de rnams chos dan ldan pa ma\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "skal ba daṅ ldan pa rnams stobs daṅ ldan pas chos daṅ ldan pa'i "
            "dpal dbaṅ daṅ ldan pa yi stobs daṅ ldan pa de rnams chos daṅ ldan pa ma",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("skal ba dan ldan pa", "skal ba daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )
        self.assertIn(
            ("stobs dan ldan pa", "stobs daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )
        self.assertIn(
            ("chos dan ldan pa", "chos daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )
        self.assertIn(
            ("dbaṅ dan ldan pa", "dbaṅ daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_phrase_allowlist_rewrites_curated_x_dan_ldan_pa_on_german_heavy_line(self) -> None:
        merged_text = (
            "ཆོས་ chos\n"
            "1. auch stobs dan ldan pa stark, mächtig, berühmt und weithin bekannt.\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "1. auch stobs daṅ ldan pa stark, mächtig, berühmt und weithin bekannt.",
            corrected,
        )

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("stobs dan ldan pa", "stobs daṅ ldan pa", "tibetan_translit_phrase_allowlist"),
            reasons,
        )

    def test_tibetan_dang_witness_does_not_touch_apostrophe_prefixed_dan(self) -> None:
        merged_text = "དང་ 'dan gsar\n"
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("དང་ 'dan gsar", corrected)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(("'dan", "'daṅ", "tibetan_dang_witness_rewrite"), reasons)

    def test_tibetan_headword_dang_witness_rewrites_latin_dan(self) -> None:
        merged_text = "འདང་ dan \\Vldan.\n"
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("འདང་ daṅ \\Vldan.", corrected)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertTrue(
            ("dan", "daṅ", "tibetan_dang_witness_rewrite") in reasons
            or (
                "འདང་ dan \\Vldan.",
                "འདང་ daṅ \\Vldan.",
                "tibetan_dang_phrase_override",
            )
            in reasons
        )

    def test_tibetan_dang_witness_does_not_fire_without_tibetan(self) -> None:
        merged_text = "dan po gsal gi don\n"
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("dan po gsal gi don", corrected)
        self.assertNotIn("daṅ po", corrected)
        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertNotIn(("dan", "daṅ", "tibetan_dang_witness_rewrite"), reasons)

    def test_exact_sanskrit_overrides_for_verified_forms(self) -> None:
        merged_text = (
            "སྐད skt. Nägärjuna Pramänakirtih Päramitäsamäsa Uddänas Mülasarvästiväda "
            "Mülasarvästi- Mahämäyürividyäräjni Astäpadikrtadhüpayoga Dhäpayoga-ratnamaälä\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn(
            "skt. Nāgārjuna Pramāṇakīrtiḥ Pāramitāsamāsa Uddānas Mūlasarvāstivāda "
            "Mūlasarvāsti- Mahāmāyūrīvidyārājñī Aṣṭapadīkṛtadhūpayoga Dhūpayogaratnamālā",
            corrected,
        )

        reasons = {(row["from_token"].lower(), row["to_token"].lower(), row["reason"]) for row in changes}
        self.assertIn(("dhäpayoga-ratnamaälä", "dhūpayogaratnamālā", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("nägärjuna", "nāgārjuna", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("pramänakirtih", "pramāṇakīrtiḥ", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("päramitäsamäsa", "pāramitāsamāsa", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("uddänas", "uddānas", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("mülasarvästiväda", "mūlasarvāstivāda", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("mülasarvästi", "mūlasarvāsti", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("mahämäyürividyäräjni", "mahāmāyūrīvidyārājñī", "sanskrit_high_freq_allowlist"), reasons)
        self.assertIn(("astäpadikrtadhüpayoga", "aṣṭapadīkṛtadhūpayoga", "sanskrit_high_freq_allowlist"), reasons)

    def test_structural_quote_wrap_direct(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "beispiel „sie vortra-\n"
            "gen das klar“ (Mil 12,3)\n"
        )
        result, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("beispiel „sie vortragen das klar“ (Mil 12,3)", corrected)
        self.assertEqual(result["structural_rewrite_count"], 1)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("vortra-/gen", "vortragen", "structural_german_quote_hyphen_wrap_direct"),
            reasons,
        )

    def test_structural_quote_wrap_with_intervening_citation(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "tschJul khrims — gos gon pas (metr.) „sie tra-\n"
            "(Gir\n"
            "\n"
            "24,24); lta ba — gi 97/ gzun nas „man legt\n"
            "eine reine Sicht zu Grunde“ (Mil 86,27);\n"
            "khon chos pa — ciig yin par ’dug „er scheint\n"
            "\n"
            "gen das Gewand einer reinen Moral“\n"
            "\n"
            "ein wahrhaft religiöser Mensch zu sein“ (Mil 128,7)\n"
        )
        result, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("„sie tragen das Gewand einer reinen Moral“ (Gir 24,24);", corrected)
        self.assertIn("lta ba — gi 97/ gzun nas „man legt", corrected)
        self.assertEqual(result["structural_rewrite_count"], 1)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("tra-/gen", "tragen", "structural_german_quote_hyphen_wrap_citation"),
            reasons,
        )

    def test_structural_quote_wrap_does_not_touch_bibliography(self) -> None:
        merged_text = (
            "Schmidt, Isaak 1841: Tibetisch-Deutsches Wörterbuch.\n"
            "Titel „Prajña-pāramitā-\n"
            "samcaya“ in bibliographischer Form.\n"
        )
        result, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("Titel „Prajña-pāramitā-\nsamcaya“ in bibliographischer Form.", corrected)
        self.assertEqual(result["structural_rewrite_count"], 0)

    def test_structural_quote_wrap_direct_stays_on_immediate_next_line(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "beispiel „Würmer, Insekten und Fi-\n"
            "sche usw. sind aus Warmem und Feuchtem\n"
            "geboren (skt. svedaja)“\n"
        )
        result, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("„Würmer, Insekten und Fische usw. sind aus Warmem und Feuchtem", corrected)
        self.assertIn("geboren (skt. svedaja)“", corrected)
        self.assertNotIn("Figeboren", corrected)
        self.assertEqual(result["structural_rewrite_count"], 1)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(
            ("Fi-/sche", "Fische", "structural_german_quote_hyphen_wrap_direct"),
            reasons,
        )

    def test_structural_quote_wrap_does_not_join_hyphenated_phrase(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "Lex. „i.S.v. von Sonnen-\n"
            "und Schattenseite“.\n"
        )
        result, corrected, _ = self.run_postprocess_fixture(merged_text)

        self.assertIn("„i.S.v. von Sonnen-\nund Schattenseite“.", corrected)
        self.assertNotIn("Sonnenund", corrected)
        self.assertEqual(result["structural_rewrite_count"], 0)


class LocCanonicalizationTests(unittest.TestCase):
    def test_loc_canonicalization_keeps_output_in_loc(self) -> None:
        self.assertEqual(pem.canonicalize_translit_token("byañ"), "byaṅ")
        self.assertEqual(pem.canonicalize_translit_token("gsañ"), "gsaṅ")
        self.assertEqual(pem.canonicalize_translit_token("kyañ"), "kyaṅ")
        self.assertEqual(pem.canonicalize_translit_token("yañ"), "yaṅ")

    def test_loc_name_piece_detection_is_diacritic_first(self) -> None:
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("śes"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("saṅs"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("lhun"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("byaṅ"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("gsaṅ"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("bzaṅ"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("dbaṅ"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("sangs"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("byang"))
        self.assertTrue(pem.token_is_likely_tibetan_name_piece("gsang"))

    def test_hyphenated_initial_i_to_l_translit_accepts_loc_forms(self) -> None:
        self.assertTrue(pem.token_is_safe_hyphenated_initial_i_to_l_translit("Rigs-Idan", "Rigs-ldan"))
        self.assertTrue(
            pem.token_is_safe_hyphenated_initial_i_to_l_translit("Bkra-śis-Ihun-po", "Bkra-śis-lhun-po")
        )
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Ita", "lta"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Iha", "lha"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Ihan", "lhan"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Ihun", "lhun"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Iho", "lho"))
        self.assertTrue(pem.token_is_initial_i_translit_candidate("Itos", "ltos"))

    def test_distinctive_loc_clusters_detected_without_wylie_shadow(self) -> None:
        self.assertTrue(bool(pem.DISTINCTIVE_TIB_CLUSTER_RE.search("gźon")))
        self.assertTrue(bool(pem.DISTINCTIVE_TIB_CLUSTER_RE.search("sñiṅ")))

    def test_ascii_translit_evidence_restores_context_without_changing_loc_output(self) -> None:
        self.assertTrue(pem.token_has_translit_cue("byang"))
        self.assertTrue(pem.token_has_translit_cue("gsang"))
        self.assertTrue(pem.token_has_translit_cue("kyang"))
        self.assertTrue(pem.token_has_translit_cue("yang"))
        self.assertTrue(pem.token_has_translit_cue("kyis"))
        self.assertTrue(pem.token_has_translit_cue("gyis"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("byang"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("gsang"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("kyang"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("yang"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("kyis"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("gyis"))

    def test_loc_short_syllables_restore_safe_ascii_translit_recall(self) -> None:
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("kyis"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("gyis"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("kyaṅ"))
        self.assertTrue(pem.token_has_distinctive_tibetan_signature("byaṅ"))

    def test_token_is_translit_like_recovers_ascii_loc_contexts(self) -> None:
        self.assertTrue(pem.token_is_translit_like("byang", line_has_tibetan=False, is_entry_start=True))
        self.assertTrue(pem.token_is_translit_like("gsang", line_has_tibetan=False, is_entry_start=True))
        self.assertTrue(pem.token_is_translit_like("kyis", line_has_tibetan=True, is_entry_start=False))
        self.assertTrue(pem.token_is_translit_like("gyis", line_has_tibetan=True, is_entry_start=False))
        self.assertTrue(pem.token_is_translit_like("lhun", line_has_tibetan=False, is_entry_start=True))
        self.assertTrue(pem.token_is_translit_like("lta", line_has_tibetan=True, is_entry_start=False))

    def test_token_is_translit_like_rejects_plain_german_or_latin_words(self) -> None:
        self.assertFalse(pem.token_is_translit_like("einen", line_has_tibetan=False, is_entry_start=True))
        self.assertFalse(pem.token_is_translit_like("Wrightia", line_has_tibetan=False, is_entry_start=True))
        self.assertFalse(
            pem.token_is_translit_like("antidysenterica", line_has_tibetan=False, is_entry_start=False)
        )


if __name__ == "__main__":
    unittest.main()

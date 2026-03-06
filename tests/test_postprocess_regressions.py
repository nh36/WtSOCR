import csv
import tempfile
import unittest
from pathlib import Path

from scripts import postprocess_entry_map as pem


class PostprocessRegressionTests(unittest.TestCase):
    def run_postprocess_fixture(self, merged_text: str) -> tuple[dict[str, object], str, list[dict[str, str]]]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            merged = root / "fixture_merged.txt"
            outdir = root / "out"
            merged.write_text(merged_text, encoding="utf-8")
            outdir.mkdir(parents=True, exist_ok=True)

            result = pem.run_one(
                merged=merged,
                audit=None,
                outdir=outdir,
                label="fixture",
                trusted_min_freq=2,
                discover_max_edit=2,
                discover_max_rare_freq=3,
            )
            corrected = Path(result["corrected_full"]).read_text(encoding="utf-8")
            with Path(result["changes_tsv"]).open(newline="", encoding="utf-8") as f:
                changes = list(csv.DictReader(f, delimiter="\t"))
            return result, corrected, changes

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

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("$in", "śin", "explicit_user_allowlist_in_tu"), reasons)
        self.assertIn(("dgra-Iba-Gottheit", "dgra-lba-Gottheit", "explicit_user_allowlist"), reasons)
        self.assertIn(("dPal-Idan", "dPal-ldan", "explicit_user_allowlist"), reasons)
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

    def test_citation_sigla_confusables_normalized(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(NOBEL 1950:12) L$dz L$dz-K Vi$T Vi$ST Vis$T Li$ Lis$ Y$'\n"
            "vgl. (NOBEL 1951:13) L$dz Vi$T Vis$T Y$\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("Lsdz", corrected)
        self.assertIn("Lsdz-K", corrected)
        self.assertIn("VisT", corrected)
        self.assertIn("Lis", corrected)
        self.assertIn("Ys'", corrected)
        self.assertIn("Ys", corrected)
        self.assertNotIn("L$dz", corrected)
        self.assertNotIn("Vi$T", corrected)
        self.assertNotIn("Vi$ST", corrected)
        self.assertNotIn("Vis$T", corrected)
        self.assertNotIn("Li$", corrected)
        self.assertNotIn("Lis$", corrected)
        self.assertNotIn("Y$", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("L$dz", "Lsdz", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("L$dz-K", "Lsdz-K", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vi$T", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vi$ST", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vis$T", "VisT", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Li$", "Lis", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Lis$", "Lis", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Y$", "Ys", "citation_siglum_confusable_map"), reasons)

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
        self.assertIn("(Lis 17,10; KlonD 739,6;", corrected)
        self.assertNotIn("Y$", corrected)
        self.assertNotIn("Li$", corrected)

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("Y$", "Ys", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Li$", "Lis", "citation_siglum_confusable_map"), reasons)

    def test_citation_sigla_extended_safe_normalization(self) -> None:
        merged_text = (
            "ཀོང་ koṅ\n"
            "(P$ 7c) (Bu-$z 51,3) (Vi$ 67b) (Vis$ 6b) ($ambh 5b6) ($PS 38) "
            "(RoIN$ 35,1) (In$ 29) (G$ 93a) (G$-H 481) (G$S-H 74a)\n"
            "(ViST 228,30) (VisST 142,4) (VIST 158,23) (VIiST 210,6) (YS 80d) (GS-H 60d)\n"
        )
        _, corrected, changes = self.run_postprocess_fixture(merged_text)

        self.assertIn("(Ps 7c)", corrected)
        self.assertIn("(Bu-Sz 51,3)", corrected)
        self.assertIn("(Vis 67b)", corrected)
        self.assertIn("(Vis 6b)", corrected)
        self.assertIn("(Sambh 5b6)", corrected)
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

        reasons = {(row["from_token"], row["to_token"], row["reason"]) for row in changes}
        self.assertIn(("P$", "Ps", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Bu-$z", "Bu-Sz", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vi$", "Vis", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("Vis$", "Vis", "citation_siglum_confusable_map"), reasons)
        self.assertIn(("$ambh", "Sambh", "citation_siglum_confusable_map"), reasons)
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

        self.assertIn("Sambh", corrected)
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
        self.assertIn(("$Sambh", "Sambh", "citation_siglum_confusable_map"), reasons)
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


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

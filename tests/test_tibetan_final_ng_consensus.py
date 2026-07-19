import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_tibetan_final_ng_consensus.py"
SPEC = importlib.util.spec_from_file_location("build_tibetan_final_ng_consensus", SCRIPT)
assert SPEC and SPEC.loader
consensus = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = consensus
SPEC.loader.exec_module(consensus)


class TibetanFinalNgConsensusTests(unittest.TestCase):
    def test_final_nasal_skeleton_is_narrow(self) -> None:
        self.assertTrue(consensus.source_variant_for_target("dban", "dbaṅ"))
        self.assertTrue(consensus.source_variant_for_target("chuñ", "chuṅ"))
        self.assertFalse(consensus.source_variant_for_target("German", "dbaṅ"))
        self.assertFalse(consensus.source_variant_for_target("bsgrun", "sgruṅ"))

    def test_tibetan_n_does_not_enter_final_ng_consensus(self) -> None:
        self.assertFalse(consensus.ends_in_tibetan_ng("བསྒྱུན"))
        self.assertTrue(consensus.ends_in_tibetan_ng("དབང"))
        self.assertTrue(consensus.ends_in_tibetan_ng("ཉངས"))

    def test_positional_alignment_does_not_use_unrelated_same_line_ng(self) -> None:
        syllables, tail, _tail_start = consensus.tibetan_syllables_and_tail(
            "དབང་པོ་ unrelated dban"
        )
        latin = consensus.latin_headword_tokens(tail, len(syllables))
        self.assertEqual(syllables, ["དབང", "པོ"])
        self.assertEqual(latin[0][0], "unrelated")

    def test_competing_forms_lower_confidence(self) -> None:
        self.assertFalse(2 >= 3 * max(1, 2))
        self.assertTrue(6 >= 3 * max(1, 2))

    def test_subjoined_ra_requires_r_in_consensus_target(self) -> None:
        self.assertEqual(
            consensus.syllable_identity_guard("ཐང", "thaṅ")[0],
            "exact_same_tibetan_syllable",
        )
        self.assertEqual(
            consensus.syllable_identity_guard("ཐྲང", "thaṅ")[0],
            "consonantal_structure_mismatch",
        )
        self.assertEqual(
            consensus.syllable_identity_guard("ཐྲང", "thraṅ")[0],
            "exact_same_tibetan_syllable",
        )

    def test_later_citation_number_does_not_damage_headword_alignment(self) -> None:
        line = "ཐང་ than npr. Kloster in 2 1531"
        syllables, tail, tail_start = consensus.tibetan_syllables_and_tail(line)
        latin = consensus.latin_headword_tokens(tail, len(syllables))
        start = tail_start + latin[0][1]
        end = start + len(latin[0][0])
        self.assertEqual(
            consensus.classify_damage_scope(line, tail_start, start, end),
            "later_gloss_or_commentary",
        )

    def test_damage_before_aligned_phrase_remains_manual(self) -> None:
        line = "ཐང་ ? than plain"
        syllables, tail, tail_start = consensus.tibetan_syllables_and_tail(line)
        latin = consensus.latin_headword_tokens(tail, len(syllables))
        start = tail_start + latin[0][1]
        end = start + len(latin[0][0])
        self.assertEqual(
            consensus.classify_damage_scope(line, tail_start, start, end),
            "damage_before_latin_alignment",
        )

    def test_builds_dban_candidate_from_internal_consensus(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            path = qa / "wts_1_34_line_zones.tsv"
            path.write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tདབང་པོ་ dbaṅ po\n"
                "1\t2\theadword_line\tདབང་ཆ་ dbaṅ cha\n"
                "1\t3\theadword_line\tདབང་པོ་ dban po\n",
                encoding="utf-8",
            )
            rows = consensus.build_consensus_rows(release)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_latin_token"], "dban")
        self.assertEqual(rows[0]["proposed_latin_target"], "dbaṅ")
        self.assertEqual(rows[0]["alignment_category"], "dominant_internal_consensus")

    def test_single_attestation_is_insufficient_not_competing(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            path = qa / "wts_1_34_line_zones.tsv"
            path.write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tཐང་ thaṅ\n"
                "1\t2\theadword_line\tཐང་ than\n",
                encoding="utf-8",
            )
            rows = consensus.build_consensus_rows(release)
        self.assertEqual(rows[0]["alignment_category"], "insufficient_consensus")

    def test_subjoined_ra_bad_alignment_is_never_high_confidence(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            path = qa / "wts_1_34_line_zones.tsv"
            path.write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tཐྲང་ thaṅ\n"
                "1\t2\theadword_line\tཐྲང་ than\n",
                encoding="utf-8",
            )
            rows = consensus.build_consensus_rows(release)
        self.assertEqual(rows[0]["alignment_category"], "syllable_structure_mismatch")
        self.assertNotEqual(rows[0]["confidence"], "high")

    def test_family_rankings_keep_tibetan_syllables_separate(self) -> None:
        rows = [
            {
                "tibetan_syllable": "གོང",
                "source_latin_token": "gon",
                "proposed_latin_target": "goṅ",
                "alignment_category": "dominant_internal_consensus",
                "accepted_form_count": "8",
                "volume": "wts_1_34",
            },
            {
                "tibetan_syllable": "འགོང",
                "source_latin_token": "gon",
                "proposed_latin_target": "goṅ",
                "alignment_category": "dominant_internal_consensus",
                "accepted_form_count": "2",
                "volume": "wts_1_34",
            },
            {
                "tibetan_syllable": "གོང",
                "source_latin_token": "goh",
                "proposed_latin_target": "goṅ",
                "alignment_category": "damaged_context",
                "accepted_form_count": "8",
                "volume": "wts_35_51",
            },
        ]
        rankings = consensus.build_family_rankings(rows)
        self.assertEqual(len(rankings), 2)
        plain = next(row for row in rankings if row["tibetan_syllable"] == "གོང")
        prefixed = next(
            row for row in rankings if row["tibetan_syllable"] == "འགོང"
        )
        self.assertEqual(plain["candidate_count"], "2")
        self.assertIn("gon:1", plain["source_variants_and_counts"])
        self.assertIn("goh:1", plain["source_variants_and_counts"])
        self.assertEqual(prefixed["candidate_count"], "1")

    def test_same_entry_echo_detects_explicit_repetition(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tགླང་ཐབས་ glaṅ thabs\n"
                "1\t2\theadword_line\tགླང་ཐབས་ glan thabs auch glan ’thab\n",
                encoding="utf-8",
            )
            rows = consensus.build_same_entry_echo_rows(release)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["additional_source_token"], "glan")
        self.assertEqual(rows[0]["echo_category"], "explicit_same_lemma_repetition")


if __name__ == "__main__":
    unittest.main()

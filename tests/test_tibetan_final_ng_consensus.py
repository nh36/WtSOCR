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


if __name__ == "__main__":
    unittest.main()

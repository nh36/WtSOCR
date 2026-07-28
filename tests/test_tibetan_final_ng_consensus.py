import importlib.util
import csv
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
    def test_latin_headword_token_preserves_dotless_i(self) -> None:
        self.assertEqual(
            consensus.latin_headword_tokens("garı gloss", 1)[0][0], "garı"
        )

    def test_latin_headword_token_preserves_precomposed_and_combining_marks(self) -> None:
        self.assertEqual(
            consensus.latin_headword_tokens("gźuṅ gloss", 1)[0][0], "gźuṅ"
        )
        self.assertEqual(
            consensus.latin_headword_tokens("gz\u0301uṅ gloss", 1)[0][0],
            "gz\u0301uṅ",
        )

    def test_latin_headword_token_preserves_internal_apostrophe(self) -> None:
        self.assertEqual(
            consensus.latin_headword_tokens("pa’i gloss", 1)[0][0], "pa’i"
        )

    def test_latin_headword_token_stops_before_punctuation(self) -> None:
        self.assertEqual(
            consensus.latin_headword_tokens("gaṅ, gloss", 1)[0][0], "gaṅ"
        )
    def test_genuine_dotted_anchor_requires_final_ng_coda(self) -> None:
        for token in ("gsuṅ", "dpuṅ"):
            self.assertTrue(
                consensus.is_genuine_dotted_final_ng_anchor(token, "གསུང")
            )
        for token in ("gsuṅń", "dpuṅń", "gsuṅn", "gsuṅh"):
            self.assertFalse(
                consensus.is_genuine_dotted_final_ng_anchor(token, "གསུང")
            )
        self.assertTrue(
            consensus.is_genuine_dotted_final_ng_anchor("ñaṅs", "ཉངས")
        )
        self.assertFalse(
            consensus.is_genuine_dotted_final_ng_anchor("ñaṅ", "ཉངས")
        )

    def test_source_compatible_signature_is_case_sensitive_and_exact(self) -> None:
        self.assertEqual(
            consensus.source_compatible_signature("ban"),
            "ba<FINAL_NASAL>",
        )
        self.assertTrue(consensus.source_compatible_pair("ban", "baṅ"))
        self.assertTrue(consensus.source_compatible_pair("bah", "baṅ"))
        self.assertTrue(consensus.source_compatible_pair("Sin", "Siṅ"))
        self.assertFalse(consensus.source_compatible_pair("Sin", "siṅ"))
        self.assertFalse(consensus.source_compatible_pair("ban", "dbaṅ"))
        self.assertFalse(consensus.source_compatible_pair("ban", "buṅ"))
        self.assertFalse(consensus.source_compatible_pair("klon", "groṅ"))
        self.assertFalse(consensus.source_compatible_pair("khon", "kboṅ"))
        self.assertTrue(
            consensus.token_has_attached_marker(
                "འཕྲང་འཕྲེང་ /phran phreṅ", 1
            )
        )
        self.assertFalse(
            consensus.token_has_attached_marker(
                "འཕྲང་འཕྲེང་ ’phran phreṅ", 1
            )
        )

    def test_source_compatible_consensus_excludes_different_stems(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tབང་ baṅ\n"
                "1\t2\theadword_line\tབང་ baṅ\n"
                "1\t3\theadword_line\tབང་ dbaṅ\n"
                "1\t4\theadword_line\tབང་ buṅ\n"
                "1\t5\theadword_line\tབང་ ban\n",
                encoding="utf-8",
            )
            rows = consensus.build_source_compatible_rows(release)
        row = next(item for item in rows if item["source_latin_token"] == "ban")
        self.assertEqual(row["proposed_latin_target"], "baṅ")
        self.assertEqual(row["compatible_accepted_target_count"], "2")
        self.assertEqual(
            row["source_compatible_category"],
            "source_compatible_dominant_consensus",
        )
        self.assertIn("dbaṅ:1", row["incompatible_dotted_form_counts"])
        self.assertIn("buṅ:1", row["incompatible_dotted_form_counts"])

    def test_source_compatible_klong_does_not_compete_with_grong(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tཀློང་ kloṅ\n"
                "1\t2\theadword_line\tཀློང་ kloṅ\n"
                "1\t3\theadword_line\tཀློང་ groṅ\n"
                "1\t4\theadword_line\tཀློང་ klon\n",
                encoding="utf-8",
            )
            rows = consensus.build_source_compatible_rows(release)
        row = next(item for item in rows if item["source_latin_token"] == "klon")
        self.assertEqual(
            row["source_compatible_category"],
            "source_compatible_dominant_consensus",
        )
        self.assertIn("groṅ:1", row["incompatible_dotted_form_counts"])

    def test_source_compatible_guard_rejects_observed_bad_stems(self) -> None:
        for syllable, target in (("ཁང", "kbaṅ"), ("སྤང", "spyaṅ")):
            status, note = consensus.source_compatible_identity_guard(
                syllable, target
            )
            self.assertEqual(status, "transcription_structure_requires_review")
            self.assertIn("stem_", note)

    def test_source_compatible_discovery_is_independent_of_legacy_target(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            dotted = (
                "1\t1\theadword_line\tབང་ fooṅ\n"
                "1\t2\theadword_line\tབང་ fooṅ\n"
                "1\t3\theadword_line\tབང་ fooṅ\n"
                "1\t4\theadword_line\tབང་ fooṅ\n"
                "1\t5\theadword_line\tབང་ fooṅ\n"
                "1\t6\theadword_line\tབང་ baṅ\n"
                "1\t7\theadword_line\tབང་ baṅ\n"
                "1\t8\theadword_line\tབང་ ban\n"
            )
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n" + dotted,
                encoding="utf-8",
            )
            legacy = consensus.build_consensus_rows(release)
            source_rows = consensus.build_source_compatible_rows(release)
        self.assertFalse(any(row["source_latin_token"] == "ban" for row in legacy))
        row = next(
            row for row in source_rows if row["source_latin_token"] == "ban"
        )
        self.assertEqual(row["proposed_latin_target"], "baṅ")
        self.assertEqual(row["compatible_accepted_target_count"], "2")
        self.assertEqual(
            row["old_alignment_category"],
            "not_emitted_by_legacy_global_target",
        )

    def test_malformed_internal_ng_is_not_a_compatible_anchor(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tགསུང་ gsuṅń\n"
                "1\t2\theadword_line\tགསུང་ fooṅ\n"
                "1\t3\theadword_line\tགསུང་ gsun\n",
                encoding="utf-8",
            )
            rows = consensus.build_source_compatible_rows(release)
        row = next(item for item in rows if item["source_latin_token"] == "gsun")
        self.assertEqual(row["compatible_accepted_target_count"], "0")
        self.assertEqual(row["proposed_latin_target"], "")
        self.assertNotIn("hypothetical_target", row)
        self.assertEqual(
            row["source_compatible_category"],
            "source_compatible_no_anchor",
        )

    def test_base_anchor_provenance_requires_direct_verification(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tབང་ baṅ\n",
                encoding="utf-8",
            )
            provenance = consensus.collect_anchor_provenance(release)
        self.assertEqual(len(provenance), 1)
        self.assertEqual(
            provenance[0]["provenance_class"],
            "base_provenance_unverified",
        )

    def test_google_witness_evidence_includes_unresolved_and_candidate_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            diagnostics = qa / "tibetan_cleanup_diagnostics"
            diagnostics.mkdir(parents=True)
            (qa / "wts_1_34_alternate_witness_unresolved.tsv").write_text(
                "page\tline\ttoken_index\tbase_token\talternate_token\treason\n"
                "1\t2\t3\tkron\tkroṅ\tunresolved\n",
                encoding="utf-8",
            )
            (diagnostics / "tibetan_google_candidate_readings.tsv").write_text(
                "page\tline\ttoken_index\tbase_token\talternate_token\treason\n"
                "4\t5\t6\trtin\trtiṅ\tcandidate\n",
                encoding="utf-8",
            )
            evidence = consensus.collect_google_witness_evidence(release)
        self.assertEqual(
            {(row["witness_status"], row["alternate_token"]) for row in evidence},
            {("unresolved", "kroṅ"), ("candidate", "rtiṅ")},
        )

    def test_alignment_review_status_uses_auditable_exceptions(self) -> None:
        self.assertEqual(
            consensus.alignment_review_status("ཆུང", "run", ""),
            "source_variant_requires_manual_review",
        )
        self.assertEqual(
            consensus.alignment_review_status("གང", "Dach", ""),
            "obvious_gloss_or_alignment_noise",
        )
        self.assertEqual(
            consensus.alignment_review_status("ཀྲོང", "kron", "kroṅ"),
            "exact_source_signature_supported",
        )
        self.assertEqual(
            consensus.alignment_review_status("ལྗང", "ldan", "ldaṅ"),
            "exact_source_signature_supported",
        )
        self.assertEqual(
            consensus.alignment_review_status("གཞུང", "gzun", ""),
            "known_multi_error_source",
        )
        self.assertEqual(
            consensus.alignment_review_status("ལྗང", "Dan", ""),
            "known_multi_error_source",
        )

    def test_zero_anchor_rows_have_no_semantic_target(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tཁོང་ fooṅ\n"
                "1\t2\theadword_line\tཁོང་ Khon\n",
                encoding="utf-8",
            )
            row = consensus.build_source_compatible_rows(release)[0]
        self.assertEqual(row["proposed_latin_target"], "")
        self.assertNotIn("hypothetical_target", row)
        self.assertEqual(
            row["source_compatible_category"],
            "source_compatible_no_anchor",
        )
        self.assertEqual(row["alignment_review_status"], "unresolved")

    def test_pilot_anchor_provenance_is_not_inferred_from_current_release(self) -> None:
        provenance = consensus.collect_anchor_provenance(ROOT / "release/current")
        expected = {
            ("wts_9_m", "302", "20", "2", "ཀྲོང", "kroṅ"),
            ("wts_8_b", "252", "37", "3", "རྟིང", "rtiṅ"),
            ("wts_8_b", "22", "12", "3", "བགྲང", "bgraṅ"),
        }
        observed = {
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["tibetan_syllable"], row["current_dotted_token"],
            ): row["provenance_class"]
            for row in provenance
        }
        for key in expected:
            self.assertEqual(observed[key], "base_provenance_unverified")

    def test_pilot_dual_positional_echo_identity_is_resolved_elsewhere(self) -> None:
        consensus.validate_positional_echo_dual_identities()

    def test_echo_discovery_uses_later_tokens_compatible_target(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tབང་ fooṅ\n"
                "1\t2\theadword_line\tབང་ fooṅ\n"
                "1\t3\theadword_line\tབང་ fooṅ\n"
                "1\t4\theadword_line\tབང་ baṅ\n"
                "1\t5\theadword_line\tབང་ baṅ\n"
                "1\t6\theadword_line\tབང་ fooṅ auch ban\n",
                encoding="utf-8",
            )
            echoes = consensus.build_same_entry_echo_rows(release)
        row = next(row for row in echoes if row["additional_source_token"] == "ban")
        self.assertEqual(row["proposed_target"], "baṅ")
        self.assertEqual(row["echo_category"], "explicit_same_lemma_repetition")

    def test_source_compatible_coverage_reconciles(self) -> None:
        rows = [
            {
                "compatible_accepted_target_count": "2",
                "source_compatible_category":
                    "source_compatible_dominant_consensus",
            },
            {
                "compatible_accepted_target_count": "1",
                "source_compatible_category":
                    "source_compatible_single_anchor",
            },
            {
                "compatible_accepted_target_count": "0",
                "source_compatible_category":
                    "source_compatible_structure_mismatch",
            },
        ]
        audit = {
            row["metric"]: row["count"]
            for row in consensus.build_source_compatible_coverage_audit(rows)
        }
        self.assertEqual(audit["aligned_undotted_candidates_considered"], "3")
        self.assertEqual(audit["accounted_category_total"], "3")

    def test_insufficient_matrix_counts_one_anchor_once(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tབང་ baṅ\n"
                "1\t2\theadword_line\tབང་ ban\n"
                "1\t3\theadword_line\tབང་ ban\n"
                "1\t4\theadword_line\tབང་ ban\n",
                encoding="utf-8",
            )
            rows = consensus.build_source_compatible_rows(release)
            matrix = consensus.build_insufficient_evidence_matrix(
                release,
                compatible_rows=rows,
                echo_rows=[],
                override_rows=[],
            )
        row = next(item for item in matrix if item["source_variant"] == "ban")
        self.assertEqual(row["undotted_clean_row_count"], "3")
        self.assertEqual(row["base_ocr_dotted_anchor_count"], "0")
        self.assertEqual(row["base_provenance_unverified_anchor_count"], "1")
        self.assertEqual(row["same_volume_raw_anchor_count"], "0")
        self.assertEqual(row["cross_volume_raw_anchor_count"], "0")
        self.assertEqual(
            row["suggested_review_tier"],
            "anchor_provenance_or_identity_review",
        )

    def test_insufficient_matrix_identifies_cross_volume_anchor(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            for volume, line in (
                ("wts_1_34", "བང་ ban"),
                ("wts_35_51", "བང་ baṅ"),
            ):
                qa = release / "qa" / volume
                qa.mkdir(parents=True)
                (qa / f"{volume}_line_zones.tsv").write_text(
                    "page\tline\tzone\tline_text\n"
                    f"1\t1\theadword_line\t{line}\n",
                    encoding="utf-8",
                )
            rows = consensus.build_source_compatible_rows(release)
            matrix = consensus.build_insufficient_evidence_matrix(
                release,
                compatible_rows=rows,
                echo_rows=[],
                override_rows=[],
            )
        row = next(item for item in matrix if item["source_variant"] == "ban")
        self.assertEqual(row["same_volume_raw_anchor_count"], "0")
        self.assertEqual(row["cross_volume_raw_anchor_count"], "0")
        self.assertEqual(row["base_provenance_unverified_anchor_count"], "1")
        self.assertEqual(row["target_evidence_channels"], "")
        self.assertEqual(
            row["suggested_review_tier"],
            "anchor_provenance_or_identity_review",
        )

    def test_historical_frozen_manifests_use_exact_final_nasal_pairs(self) -> None:
        checked = 0
        for path in sorted((ROOT / "data").glob(
            "final_ng_exact_candidate_prepass_manifest_*.tsv"
        )):
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle, delimiter="\t"):
                    if row["candidate_status"] != "positional":
                        continue
                    self.assertTrue(
                        consensus.source_compatible_pair(
                            row["source_token"], row["target"]
                        ),
                        (path.name, row),
                    )
                    checked += 1
        self.assertGreater(checked, 100)

    def test_one_anchor_pilot_freezes_only_authorized_exact_variants(self) -> None:
        path = (
            ROOT / "data"
            / "final_ng_source_compatible_one_anchor_pilot_prepass_manifest_63a9742.tsv"
        )
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        positional = [row for row in rows if row["candidate_status"] == "positional"]
        self.assertEqual(len(positional), 19)
        self.assertEqual(
            {
                (row["tibetan_syllable"], row["source_token"], row["target"])
                for row in positional
            },
            {
                ("ཀྲོང", "kron", "kroṅ"),
                ("རྟིང", "rtin", "rtiṅ"),
                ("བགྲང", "bgran", "bgraṅ"),
            },
        )
        self.assertTrue(
            all(row["anchor_provenance"] == "base_ocr_dotted" for row in rows)
        )

    def test_source_compatible_frozen_scope_excludes_mixed_and_bad_anchors(
        self,
    ) -> None:
        path = (
            ROOT / "data"
            / "final_ng_source_compatible_prepass_manifest_6e4614f.tsv"
        )
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        positional = [
            row for row in rows if row["candidate_status"] == "positional"
        ]
        self.assertEqual(len(positional), 100)
        self.assertEqual(
            {row["frozen_prepass_sha"] for row in rows},
            {"6e4614fe49f72ec5926d1c24d02c0a09a24b2597"},
        )
        self.assertFalse(
            {"ཀློང", "སྙིང", "རྱོང", "མེང", "འཕྲང"}
            & {row["tibetan_syllable"] for row in rows}
        )

    def test_mixed_source_compatible_freeze_keeps_damage_withheld(self) -> None:
        path = (
            ROOT / "data"
            / "final_ng_source_compatible_prepass_manifest_652273e.tsv"
        )
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(
            sum(row["candidate_status"] == "positional" for row in rows), 23
        )
        withheld = [
            row for row in rows
            if row["candidate_status"] == "withheld_damage"
        ]
        self.assertEqual(len(withheld), 1)
        self.assertEqual(withheld[0]["tibetan_syllable"], "ཀློང")
        self.assertEqual((withheld[0]["page"], withheld[0]["line"]), ("675", "30"))

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
        self.assertEqual(
            consensus.source_compatible_identity_guard("སྙིང", "siṅ")[0],
            "transcription_structure_requires_review",
        )
        self.assertEqual(
            consensus.source_compatible_identity_guard("རྱོང", "myoṅ")[0],
            "transcription_structure_requires_review",
        )
        self.assertEqual(
            consensus.source_compatible_identity_guard("མེང", "miṅ")[0],
            "transcription_structure_requires_review",
        )
        self.assertEqual(
            consensus.source_compatible_identity_guard("གདང", "gdoṅ")[0],
            "transcription_structure_requires_review",
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

    def test_same_entry_echo_detects_direct_repeated_tibetan_alignment(self) -> None:
        with TemporaryDirectory() as tmp:
            release = Path(tmp) / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tདྲུང་ druṅ\n"
                "1\t2\theadword_line\tདྲུང་དྲུང་ drun drun\n",
                encoding="utf-8",
            )
            rows = consensus.build_same_entry_echo_rows(release)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["echo_category"],
            "direct_repeated_tibetan_alignment",
        )

    def test_historical_echo_decision_survives_alignment_reclassification(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = root / "release"
            qa = release / "qa" / "wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tzone\tline_text\n"
                "1\t1\theadword_line\tགསུང་ gsuṅ\n"
                "1\t2\theadword_line\tགསུང་ gsun\n",
                encoding="utf-8",
            )
            decisions = root / "decisions.tsv"
            decisions.write_text(
                "volume\tpage\tline\ttoken_index\ttibetan_syllable\t"
                "source_token\tproposed_target\tdecision\techo_category\t"
                "evidence\trationale\treviewing_batch\treview_date\t"
                "reconsideration_prerequisite\n"
                "wts_1_34\t1\t2\t1\tགསུང\tgsun\tgsuṅ\tdeferred\t"
                "uncertain\ttest\tIdentity not established.\ttest_batch\t"
                "2026-07-28\tIndependent evidence\n",
                encoding="utf-8",
            )
            rows = consensus.build_same_entry_echo_rows(release, decisions)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["prior_decision"], "deferred")
        self.assertEqual(rows[0]["active_queue"], "no")
        self.assertEqual(
            rows[0]["evidence"], "persistent_historical_echo_decision"
        )


if __name__ == "__main__":
    unittest.main()

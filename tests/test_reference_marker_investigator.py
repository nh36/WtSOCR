import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMOTER_PATH = ROOT / "scripts" / "promote_reference_marker_candidates.py"
SPEC = importlib.util.spec_from_file_location("promote_reference_marker_candidates", PROMOTER_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Could not load promote_reference_marker_candidates from {PROMOTER_PATH}")
promoter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = promoter
SPEC.loader.exec_module(promoter)


def decision(**updates: str):
    row = {
        "volume": "wts_1_34",
        "page": "10",
        "line": "5",
        "diagnostic_token_index": "4",
        "token_index": "4",
        "source_token": "Tfoo",
        "marker_source": "T",
        "marker_target": "",
        "attached_token": "foo",
        "current_lemma": "bar",
        "current_lemma_ordinal": "10",
        "current_lemma_ref": "wts_1_34 10:1",
        "referenced_lemma_candidate": "foo",
        "referenced_lemma": "foo",
        "referenced_lemma_ordinal": "",
        "referenced_lemma_ref": "",
        "referenced_lemma_match_count": "1",
        "referenced_lemma_ordinal_min": "3",
        "referenced_lemma_ordinal_max": "3",
        "matched_lemma_ordinals": "3",
        "direction_resolution": "",
        "lemma_lookup_status": "unique_match",
        "referenced_lemma_lookup_key": "foo",
        "referenced_lemma_alias_matched": "foo",
        "lemma_alias_basis": "normalized|normalized",
        "exact_occurrence_status": "unique",
        "context_type": "reference_cue",
        "direction_basis": "",
        "replacement_target": "",
        "candidate_family": "ocr_prefix_T_reference_marker_candidate",
        "similar_to_promoted_family": "",
        "context_excerpt": "vgl. Tfoo.",
        "near_vgl": "1",
        "near_headword": "0",
        "near_transliteration": "1",
        "near_tibetan_script": "0",
        "decision": "defer",
        "defer_reason": "tier_a_score_below_threshold",
        "decision_notes": "",
        "score": "90",
        "positive_evidence": "unique_referenced_lemma_match;known_current_lemma",
        "negative_evidence": "",
        "tier": "",
    }
    row.update(updates)
    return promoter.CandidateDecision(**row)


def release_lines(line: str = "vgl. Tfoo.") -> dict[tuple[str, str, str], str]:
    return {
        ("wts_1_34", "10", "3"): "before two",
        ("wts_1_34", "10", "4"): "before one",
        ("wts_1_34", "10", "5"): line,
        ("wts_1_34", "10", "6"): "after one",
        ("wts_1_34", "10", "7"): "after two",
    }


class ReferenceMarkerInvestigatorTests(unittest.TestCase):
    def investigate(self, candidate, line: str = "vgl. Tfoo.", reviewed=None):
        return promoter.investigate_decision(
            candidate,
            release_lines(line),
            reviewed or [],
            "reference_marker_test",
        )

    def test_lemma_order_proof_promotes_reference_context(self) -> None:
        row = self.investigate(decision())

        self.assertEqual(row["decision"], "promote_exact")
        self.assertEqual(row["proof_type"], "lemma_order")
        self.assertEqual(row["reviewed_to_token"], "↑ foo")
        self.assertEqual(row["direction_basis"], "3 < 10")
        self.assertEqual(row["context_before_1"], "before one")

    def test_ordinary_context_rejected_even_with_same_side_lemma_order(self) -> None:
        row = self.investigate(
            decision(
                context_type="ordinary_example_context",
                context_excerpt="Tfoo in an example phrase.",
                near_vgl="0",
                defer_reason="ordinary_example_context",
            ),
            line="Tfoo in an example phrase.",
        )

        self.assertEqual(row["decision"], "reject_not_marker")
        self.assertIn("ordinary prose/example", row["proof_note"])
        self.assertEqual(row["reviewed_to_token"], "")

    def test_same_lemma_rejected(self) -> None:
        row = self.investigate(
            decision(
                defer_reason="same_lemma",
                matched_lemma_ordinals="10",
                referenced_lemma_ordinal_min="10",
                referenced_lemma_ordinal_max="10",
            )
        )

        self.assertEqual(row["decision"], "reject_not_marker")
        self.assertIn("current lemma", row["proof_note"])

    def test_ambiguous_crossing_rejected(self) -> None:
        row = self.investigate(
            decision(
                defer_reason="ambiguous_crosses_current",
                matched_lemma_ordinals="3;12",
                referenced_lemma_ordinal_min="3",
                referenced_lemma_ordinal_max="12",
            )
        )

        self.assertEqual(row["decision"], "reject_not_marker")
        self.assertIn("direction is unproved", row["proof_note"])

    def test_ambiguous_same_side_lemma_order_needs_source_image(self) -> None:
        row = self.investigate(
            decision(
                referenced_lemma="",
                referenced_lemma_match_count="12",
                matched_lemma_ordinals="1;2;3;4",
                defer_reason="ambiguous_replacement_target",
                context_type="reference_list_context",
            )
        )

        self.assertEqual(row["decision"], "needs_source_image")
        self.assertEqual(row["reviewed_to_token"], "")

    def test_nonunique_source_rejected(self) -> None:
        row = self.investigate(decision(exact_occurrence_status="ambiguous"))

        self.assertEqual(row["decision"], "reject_not_marker")
        self.assertIn("not uniquely located", row["proof_note"])

    def test_likely_initial_i_or_l_rejected(self) -> None:
        row = self.investigate(
            decision(
                source_token="Idan",
                marker_source="I",
                attached_token="dan",
                defer_reason="possible_ldan_not_marker",
            )
        )

        self.assertEqual(row["decision"], "reject_not_marker")
        self.assertIn("Initial-I/l", row["proof_note"])

    def test_sibling_marker_proof_promotes_local_list(self) -> None:
        row = self.investigate(
            decision(
                referenced_lemma="",
                referenced_lemma_match_count="0",
                matched_lemma_ordinals="",
                context_type="near_actual_marker_control",
                context_excerpt="foo ↑ bar; Tfoo baz",
                defer_reason="no_referenced_lemma_match",
            ),
            line="foo ↑ bar; Tfoo baz",
        )

        self.assertEqual(row["decision"], "promote_exact")
        self.assertEqual(row["proof_type"], "sibling_marker")
        self.assertEqual(row["reviewed_to_token"], "↑ foo")

    def test_same_family_reviewed_proof_promotes_local_pattern(self) -> None:
        reviewed = [
            promoter.ReviewedReferencePattern(
                marker_source="T",
                attached_key=promoter.normalize_key("foo"),
                target_marker="↓",
                target_token="foo",
                volume="wts_1_34",
                page="10",
                line="3",
                from_token="Tfoo",
                to_token="↓ foo",
            )
        ]
        row = self.investigate(
            decision(
                referenced_lemma="",
                referenced_lemma_match_count="0",
                matched_lemma_ordinals="",
                context_type="reference_list_context",
                context_excerpt="foo; Tfoo",
                defer_reason="no_referenced_lemma_match",
            ),
            line="foo; Tfoo",
            reviewed=reviewed,
        )

        self.assertEqual(row["decision"], "promote_exact")
        self.assertEqual(row["proof_type"], "same_family_reviewed")
        self.assertEqual(row["reviewed_to_token"], "↓ foo")

    def test_investigation_packet_rejects_missing_proof_or_target(self) -> None:
        base = {
            "decision": "promote_exact",
            "proof_type": "",
            "reviewed_to_token": "↑ foo",
            "marker_source": "T",
        }

        with self.assertRaisesRegex(ValueError, "concrete proof"):
            promoter.investigation_packet_row(base, "reference_marker_test")

        with self.assertRaisesRegex(ValueError, "reviewed_to_token"):
            promoter.investigation_packet_row(
                {**base, "proof_type": "lemma_order", "reviewed_to_token": ""},
                "reference_marker_test",
            )

    def test_packet_rows_from_investigation_builds_exact_override(self) -> None:
        row = self.investigate(decision())
        packet_rows = promoter.packet_rows_from_investigation([row], "reference_marker_test")

        self.assertEqual(len(packet_rows), 1)
        self.assertEqual(packet_rows[0]["from_token"], "Tfoo")
        self.assertEqual(packet_rows[0]["to_token"], "↑ foo")
        self.assertEqual(packet_rows[0]["reason"], promoter.REFERENCE_MARKER_REASON)
        self.assertTrue(packet_rows[0]["evidence"].endswith(":lemma_order"))


if __name__ == "__main__":
    unittest.main()

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_four_volume_residual_error_ledger.py"
SPEC = importlib.util.spec_from_file_location("build_four_volume_residual_error_ledger", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Could not load build_four_volume_residual_error_ledger module from {SCRIPT_PATH}")
ledger = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ledger
SPEC.loader.exec_module(ledger)


def write_tsv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class FourVolumeResidualErrorLedgerTests(unittest.TestCase):
    def test_builds_ranked_outputs_and_quarantines_validator_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "input"
            output = Path(tmp) / "output"
            write_tsv(
                root / "wts_9_m" / "tibetan_orthography_damage_candidates.tsv",
                [
                    "volume",
                    "page",
                    "line",
                    "token",
                    "candidate_family",
                    "proposed_target",
                    "context_excerpt",
                    "evidence",
                    "confidence",
                    "suggested_action",
                    "score",
                    "score_explanation",
                ],
                [
                    {
                        "volume": "wts_9_m",
                        "page": "68",
                        "line": "18",
                        "token": "dnos",
                        "candidate_family": "dngos_family",
                        "proposed_target": "dṅos",
                        "context_excerpt": "chos dnos po'i mtshan nyid",
                        "evidence": "reviewed_context",
                        "confidence": "high",
                        "suggested_action": "exact_promotion_candidate",
                        "score": "90",
                        "score_explanation": "test",
                    }
                ],
            )
            write_tsv(
                root / "qa" / "live_validator_only_residue.tsv",
                ["source", "reason_or_issue", "suggestion", "evidence_scope", "token", "page", "line"],
                [
                    {
                        "source": "validator",
                        "reason_or_issue": "reciprocal_validator_row",
                        "suggestion": "mkha'i",
                        "evidence_scope": "line",
                        "token": "mkhai",
                        "page": "1",
                        "line": "2",
                    }
                ],
            )

            ledger.build_outputs([root], output, "2026-06-25")

            promotion_rows = read_tsv(output / "four_volume_promotion_candidates.tsv")
            self.assertEqual(len(promotion_rows), 1)
            self.assertEqual(promotion_rows[0]["source_token"], "dnos")
            self.assertEqual(promotion_rows[0]["target_token"], "dṅos")

            all_rows = read_tsv(output / "four_volume_residual_error_ledger.tsv")
            validator_rows = [row for row in all_rows if row["source_token"] == "mkhai"]
            self.assertEqual(len(validator_rows), 1)
            self.assertEqual(validator_rows[0]["bucket"], "validator_only_noise")
            self.assertEqual(validator_rows[0]["recommended_action"], "ignore_validator_only")
            self.assertEqual(validator_rows[0]["risk"], "not_candidate")

    def test_sigla_policy_and_source_review_outputs_are_separated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "input"
            output = Path(tmp) / "output"
            write_tsv(
                root / "wts_9_m" / "sigla_variant_candidates.tsv",
                [
                    "source_queue",
                    "volume",
                    "page",
                    "line",
                    "token_index",
                    "source_token",
                    "proposed_canon",
                    "work_title",
                    "intro_line_ref",
                    "status",
                    "context_excerpt",
                    "suggested_action",
                ],
                [
                    {
                        "source_queue": "sigla",
                        "volume": "wts_9_m",
                        "page": "1",
                        "line": "2",
                        "token_index": "3",
                        "source_token": "G$-H",
                        "proposed_canon": "Gś-H",
                        "work_title": "bibliographic title",
                        "intro_line_ref": "intro",
                        "status": "variant",
                        "context_excerpt": "(G$-H 51)",
                        "suggested_action": "siglum_policy_review",
                    }
                ],
            )
            write_tsv(
                root / "wts_8_b" / "wts_8_b_watchdog_flags.tsv",
                ["page", "line", "entry_id", "zone", "from_token", "to_token", "tier", "reason", "watchdog_flags", "line_excerpt"],
                [
                    {
                        "page": "4",
                        "line": "5",
                        "entry_id": "e",
                        "zone": "body",
                        "from_token": "jnaurasab",
                        "to_token": "jinaurasaḥ",
                        "tier": "4",
                        "reason": "reviewed",
                        "watchdog_flags": "high_edit",
                        "line_excerpt": "source review needed",
                    }
                ],
            )

            ledger.build_outputs([root], output, "2026-06-25")

            policy_rows = read_tsv(output / "four_volume_policy_decisions_needed.tsv")
            self.assertEqual(len(policy_rows), 1)
            self.assertEqual(policy_rows[0]["source_token"], "G$-H")
            self.assertEqual(policy_rows[0]["target_token"], "Gś-H")

            source_review_rows = read_tsv(output / "four_volume_source_review_needed.tsv")
            self.assertEqual(len(source_review_rows), 1)
            self.assertEqual(source_review_rows[0]["source_token"], "jnaurasab")

            summary = (output / "four_volume_error_budget_summary.md").read_text(encoding="utf-8")
            self.assertIn("Google Vision remains an alternate witness only", summary)

    def test_google_sampling_is_not_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "input"
            output = Path(tmp) / "output"
            write_tsv(
                root / "wts_8_b" / "tibetan_google_candidate_readings.tsv",
                [
                    "volume",
                    "page",
                    "line",
                    "token_index",
                    "base_token",
                    "alternate_token",
                    "proposed_target",
                    "reason",
                    "base_key",
                    "alternate_key",
                    "candidate_family",
                    "context_excerpt",
                    "alternate_line",
                    "evidence",
                    "confidence",
                    "suggested_action",
                    "score",
                    "score_explanation",
                    "alignment_method",
                    "alignment_attribution",
                    "resynchronization_attribution",
                ],
                [
                    {
                        "volume": "wts_8_b",
                        "page": "10",
                        "line": "11",
                        "token_index": "2",
                        "base_token": "Ita",
                        "alternate_token": "lta",
                        "proposed_target": "lta",
                        "reason": "alternate_witness_unresolved",
                        "base_key": "ita",
                        "alternate_key": "lta",
                        "candidate_family": "lta_family",
                        "context_excerpt": "de ltar Ita bu",
                        "alternate_line": "de ltar lta bu",
                        "evidence": "google",
                        "confidence": "medium",
                        "suggested_action": "review",
                        "score": "50",
                        "score_explanation": "test",
                        "alignment_method": "token",
                        "alignment_attribution": "direct_page_alignment",
                        "resynchronization_attribution": "none",
                    }
                ],
            )

            ledger.build_outputs([root], output, "2026-06-25")

            promotion_rows = read_tsv(output / "four_volume_promotion_candidates.tsv")
            self.assertEqual(promotion_rows, [])

            sampling_rows = read_tsv(output / "four_volume_google_sampling_targets.tsv")
            self.assertEqual(len(sampling_rows), 1)
            self.assertEqual(sampling_rows[0]["source_token"], "Ita")
            self.assertEqual(sampling_rows[0]["recommended_action"], "sample_further")

            summary = (output / "four_volume_error_budget_summary.md").read_text(encoding="utf-8")
            self.assertIn("Ita", summary)
            self.assertIn("lta", summary)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "scripts" / "exact_promotion_batch.py"
SPEC = importlib.util.spec_from_file_location("exact_promotion_batch", HELPER_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Could not load exact_promotion_batch module from {HELPER_PATH}")
helper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = helper
SPEC.loader.exec_module(helper)


def override_row(**updates: str) -> dict[str, str]:
    row = {
        "volume": "wts_1_34",
        "page": "1",
        "line": "1",
        "token_index": "2",
        "from_token": "\\foo",
        "to_token": "↓ foo",
        "reason": "reviewed_tibetan_exact_reference_marker",
        "evidence": "test_batch",
        "review_note": "exact test row",
        "batch_id": "reference_marker_test",
        "score": "100",
        "source_diagnostic": "release/current/qa/wts_1_34/tibetan_cleanup_diagnostics/reference_marker_candidates.tsv",
        "candidate_family": "ocr_prefix_backslash_reference_marker_candidate",
        "direction_basis": "1 > 0",
        "context_type": "reference_cue",
        "positive_evidence": "unique_exact_marker_occurrence",
        "negative_evidence": "",
    }
    row.update(updates)
    return row


class ExactPromotionBatchTests(unittest.TestCase):
    def write_release_line(self, root: Path, line: str) -> None:
        text_dir = root / "release" / "current" / "text"
        text_dir.mkdir(parents=True)
        (text_dir / "wts_1_34_corrected_full.txt").write_text(line + "\n", encoding="utf-8")

    def test_validate_packet_rows_accepts_unique_prefixed_token(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_release_line(root, "one \\foo two")

            helper.validate_packet_rows(
                root,
                [override_row()],
                expected_reason="reviewed_tibetan_exact_reference_marker",
                min_score=100,
            )

    def test_validate_packet_rows_rejects_stale_source_token(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_release_line(root, "one foo two")

            with self.assertRaisesRegex(ValueError, "stale or ambiguous"):
                helper.validate_packet_rows(
                    root,
                    [override_row()],
                    expected_reason="reviewed_tibetan_exact_reference_marker",
                    min_score=100,
                )

    def test_validate_packet_rows_allows_existing_idempotent_row(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_release_line(root, "one ↓ foo two")
            ledger = root / "data" / "reviewed_tibetan_exact_overrides.tsv"
            helper.write_tsv(ledger, [override_row()], helper.OVERRIDE_FIELDS)

            helper.validate_packet_rows(
                root,
                [override_row()],
                override_path=ledger,
                expected_reason="reviewed_tibetan_exact_reference_marker",
                min_score=100,
            )

    def test_append_override_rows_skips_duplicate_and_rejects_conflict(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "reviewed_tibetan_exact_overrides.tsv"
            helper.write_tsv(path, [override_row()], helper.OVERRIDE_FIELDS)

            self.assertEqual(helper.append_override_rows(path, [override_row()]), 0)
            with self.assertRaisesRegex(ValueError, "Conflicting exact override"):
                helper.append_override_rows(path, [override_row(to_token="↑ foo")])

    def test_append_manifest_row_writes_header_and_row(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.tsv"
            helper.append_manifest_row(
                path,
                {
                    "batch_id": "reference_marker_test",
                    "family_id": "reference_marker",
                    "status": "applied",
                    "selected_count": "1",
                    "applied_count": "1",
                },
            )

            rows = helper.read_tsv(path)
            self.assertEqual(rows[0]["batch_id"], "reference_marker_test")
            self.assertEqual(rows[0]["family_id"], "reference_marker")
            self.assertEqual(rows[0]["status"], "applied")


if __name__ == "__main__":
    unittest.main()

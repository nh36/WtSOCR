import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "scripts" / "reference_marker_source_review.py"
SPEC = importlib.util.spec_from_file_location("reference_marker_source_review", HELPER_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Could not load reference_marker_source_review from {HELPER_PATH}")
helper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = helper
SPEC.loader.exec_module(helper)


def write_release_line(root: Path, line: str, volume: str = "wts_1_34") -> None:
    text_dir = root / "release" / "current" / "text"
    text_dir.mkdir(parents=True)
    (text_dir / f"{volume}_corrected_full.txt").write_text(line + "\n", encoding="utf-8")


def write_source_pdfs(root: Path) -> None:
    data_dir = root / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "source_pdfs.tsv").write_text(
        "\t".join(["label", "filename", "pages", "size_bytes", "sha256", "status", "note"])
        + "\n"
        + "\t".join(
            [
                "WtS_1-34",
                "pdfs/WtS 1-34.pdf",
                "1352",
                "0",
                "test",
                "ingested",
                "fixture",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def investigation_row(**updates: str) -> dict[str, str]:
    row = {
        "volume": "wts_1_34",
        "page": "1",
        "line": "1",
        "token_index": "2",
        "source_token": "Tfoo",
        "marker_source": "T",
        "attached_token": "foo",
        "candidate_family": "ocr_prefix_T_reference_marker_candidate",
        "context_line": "one Tfoo two",
        "decision": "needs_source_image",
        "score": "90",
    }
    row.update(updates)
    return row


def review_row(**updates: str) -> dict[str, str]:
    row = {
        "volume": "wts_1_34",
        "page": "1",
        "line": "1",
        "token_index": "2",
        "source_token": "Tfoo",
        "current_line": "one Tfoo two",
        "source_marker": "T",
        "attached_token": "foo",
        "candidate_family": "ocr_prefix_T_reference_marker_candidate",
        "context_excerpt": "one Tfoo two",
        "proposed_to_token": "",
        "source_pdf": "pdfs/WtS 1-34.pdf",
        "pdf_page": "1",
        "source_crop": "work/source_crops/test.png",
        "crop_confidence": "not_rendered",
        "source_image_decision": "",
        "source_image_marker": "",
        "review_note": "",
        "batch_id": "reference_marker_source_review_test",
        "reviewed_at": "",
    }
    row.update(updates)
    return row


class ReferenceMarkerSourceReviewTests(unittest.TestCase):
    def test_build_review_rows_selects_needs_source_image(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source_pdfs(root)

            rows = helper.build_review_rows(
                root,
                [investigation_row()],
                batch_id="reference_marker_source_review_test",
                work_dir=root / "work" / "source_review",
                limit=5,
                max_per_volume=5,
                render_crops=False,
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_pdf"], "pdfs/WtS 1-34.pdf")
            self.assertEqual(rows[0]["pdf_page"], "1")
            self.assertEqual(rows[0]["source_crop"], "work/source_review/source_crops/reference_marker_source_review_test_wts_1_34_p0001_l001_t02_Tfoo.png")
            self.assertEqual(rows[0]["crop_confidence"], "not_rendered")
            self.assertEqual(rows[0]["source_image_decision"], "")
            self.assertEqual(rows[0]["proposed_to_token"], "")

    def test_accepted_review_imports_exact_packet_row(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_release_line(root, "one Tfoo two")
            write_source_pdfs(root)

            packet_rows = helper.packet_rows_from_accepted_reviews(
                root,
                [
                    review_row(
                        source_image_decision="accept_exact",
                        source_image_marker="↑",
                        proposed_to_token="↑ foo",
                        review_note="source image shows upward marker before foo",
                        reviewed_at="2026-08-15T12:00:00Z",
                    )
                ],
                batch_id="reference_marker_source_apply_test",
                limit=5,
                max_per_volume=5,
            )

            self.assertEqual(len(packet_rows), 1)
            self.assertEqual(packet_rows[0]["from_token"], "Tfoo")
            self.assertEqual(packet_rows[0]["to_token"], "↑ foo")
            self.assertEqual(packet_rows[0]["reason"], "reviewed_tibetan_exact_reference_marker")
            self.assertEqual(packet_rows[0]["score"], "100")
            self.assertTrue(packet_rows[0]["evidence"].startswith("reference_marker_source_image:"))
            self.assertIn("source_image_marker=↑", packet_rows[0]["direction_basis"])

    def test_stale_current_line_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_release_line(root, "one Tfoo changed")
            write_source_pdfs(root)

            errors = helper.validate_review_rows(root, [review_row()])

            self.assertTrue(any("stale current_line" in error for error in errors))

    def test_applied_accepted_review_row_validates_after_exact_replacement(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_release_line(root, "one ↑ foo two")
            write_source_pdfs(root)

            errors = helper.validate_review_rows(
                root,
                [
                    review_row(
                        source_image_decision="accept_exact",
                        source_image_marker="↑",
                        proposed_to_token="↑ foo",
                        review_note="source image shows upward marker before foo",
                        reviewed_at="2026-08-15T12:00:00Z",
                    )
                ],
            )

            self.assertEqual(errors, [])

    def test_applied_accepted_review_row_still_rejects_nonmatching_line(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_release_line(root, "one ↑ bar two")
            write_source_pdfs(root)

            errors = helper.validate_review_rows(
                root,
                [
                    review_row(
                        source_image_decision="accept_exact",
                        source_image_marker="↑",
                        proposed_to_token="↑ foo",
                        review_note="source image shows upward marker before foo",
                        reviewed_at="2026-08-15T12:00:00Z",
                    )
                ],
            )

            self.assertTrue(any("stale current_line" in error for error in errors))

    def test_marker_mismatch_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_release_line(root, "one Tfoo two")
            write_source_pdfs(root)

            errors = helper.validate_review_rows(
                root,
                [
                    review_row(
                        source_image_decision="accept_exact",
                        source_image_marker="↑",
                        proposed_to_token="↓ foo",
                        review_note="source image reviewed",
                        reviewed_at="2026-08-15T12:00:00Z",
                    )
                ],
            )

            self.assertTrue(
                any("does not start with confirmed marker" in error for error in errors)
            )

    def test_pending_review_row_validates_when_current_and_unique(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_release_line(root, "one Tfoo two")
            write_source_pdfs(root)

            self.assertEqual(helper.validate_review_rows(root, [review_row()]), [])


if __name__ == "__main__":
    unittest.main()

import csv
import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_residual_review_ledgers.py"
SPEC = importlib.util.spec_from_file_location("check_residual_review_ledgers", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class ResidualReviewLedgerTests(unittest.TestCase):
    def test_checked_in_ledgers_match_current_release(self) -> None:
        errors = validator.validate_ledgers(
            ROOT / "release/current",
            ROOT / "data/residual_aligned_line_damage.tsv",
            ROOT / "data/dublin_source_image_review.tsv",
        )
        self.assertEqual(errors, [])

    def test_stale_current_line_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            qa = root / "release/qa/wts_1_34"
            qa.mkdir(parents=True)
            (qa / "wts_1_34_line_zones.tsv").write_text(
                "page\tline\tline_text\n1\t1\tཐང་ thaṅ\n",
                encoding="utf-8",
            )
            for volume in ("wts_35_51", "wts_8_b", "wts_9_m"):
                volume_qa = root / "release/qa" / volume
                volume_qa.mkdir(parents=True)
                (volume_qa / f"{volume}_line_zones.tsv").write_text(
                    "page\tline\tline_text\n",
                    encoding="utf-8",
                )
            residual = root / "residual.tsv"
            residual.write_text(
                "volume\tpage\tline\tcorrected_exact_tokens\tcurrent_line\t"
                "remaining_damaged_segment\tclassification\tinternal_evidence\t"
                "next_action\n"
                "wts_1_34\t1\t1\tthan → thaṅ\tཐང་ than\t\t"
                "later_gloss_or_commentary_damage\tevidence\tretain\n",
                encoding="utf-8",
            )
            dublin = root / "dublin.tsv"
            with dublin.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                writer.writerow(
                    [
                        "volume", "page", "line", "current_tibetan_ocr",
                        "current_latin_ocr", "proposed_alternatives",
                        "feature_to_inspect", "reason_internal_evidence_insufficient",
                    ]
                )
            errors = validator.validate_ledgers(
                root / "release",
                residual,
                dublin,
            )
        self.assertTrue(any("current_line is stale" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

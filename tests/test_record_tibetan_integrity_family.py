import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/record_tibetan_integrity_family.py"
SPEC = importlib.util.spec_from_file_location("record_integrity_test", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class RecordIntegrityFamilyTests(unittest.TestCase):
    def test_refuses_unsupported_arbitrary_target(self) -> None:
        with self.assertRaises(ValueError):
            module.validate_authorization("ཀ", {"ka"}, "invented", False)

    def test_explicit_manual_review_is_distinct_escape_hatch(self) -> None:
        module.validate_authorization("ཀ", {"ka"}, "explicit", True)

    def test_accepts_authorized_canonical_confusion(self) -> None:
        module.validate_authorization("བཞི", {"bZi"}, "bźi", False)

    def test_root_change_requires_occurrence_identity_evidence(self) -> None:
        with self.assertRaises(ValueError):
            module.require_occurrence_identity_evidence(
                "reviewed_tibetan_exact_manual_structural_root_ocr",
                True,
                None,
            )

    def test_root_change_accepts_occurrence_identity_evidence(self) -> None:
        module.require_occurrence_identity_evidence(
            "reviewed_tibetan_exact_manual_structural_root_ocr",
            True,
            "exact sibling establishes this occurrence identity",
        )

    def test_non_root_review_does_not_require_identity_evidence(self) -> None:
        module.require_occurrence_identity_evidence(
            "reviewed_tibetan_exact_manual_structural_vowel_ocr",
            True,
            None,
        )


if __name__ == "__main__":
    unittest.main()

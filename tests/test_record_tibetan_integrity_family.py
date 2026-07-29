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
    @staticmethod
    def attribution(
        role: str = "root_consonant",
        *,
        status: str = "structurally_attributed",
        extra: str = "no",
    ) -> dict[str, str]:
        return {
            "target_structural_role": role,
            "attribution_status": status,
            "extra_source_material": extra,
        }

    def test_refuses_unsupported_arbitrary_target(self) -> None:
        with self.assertRaises(ValueError):
            module.validate_authorization("ཀ", {"ka"}, "invented", False)

    def test_explicit_manual_review_is_distinct_escape_hatch(self) -> None:
        module.validate_authorization("ཀ", {"ka"}, "explicit", True)

    def test_accepts_authorized_canonical_confusion(self) -> None:
        module.validate_authorization("བཞི", {"bZi"}, "bźi", False)

    def test_root_change_requires_occurrence_identity_evidence(self) -> None:
        status = module.root_change_status([self.attribution()])
        with self.assertRaises(ValueError):
            module.require_occurrence_identity_evidence(
                True,
                status,
                None,
                None,
                None,
            )

    def test_root_change_accepts_occurrence_identity_evidence(self) -> None:
        self.assertTrue(module.require_occurrence_identity_evidence(
            True,
            module.root_change_status([self.attribution()]),
            None,
            "exact_repeated_headword",
            "exact sibling establishes this occurrence identity",
        ))

    def test_non_root_review_does_not_require_identity_evidence(self) -> None:
        self.assertFalse(module.require_occurrence_identity_evidence(
            True,
            module.root_change_status([
                self.attribution("vowel"),
                self.attribution("suffix_coda"),
            ]),
            None,
            None,
            None,
        ))

    def test_multi_error_root_change_is_reason_independent(self) -> None:
        # Regression shape: g→k at the root plus n→ṅ at the suffix.  A
        # manual_multi_error reason must not bypass the root identity gate.
        status = module.root_change_status([
            self.attribution("root_consonant"),
            self.attribution("suffix_coda"),
        ])
        with self.assertRaises(ValueError):
            module.require_occurrence_identity_evidence(
                True, status, None, None, None
            )
        self.assertTrue(module.require_occurrence_identity_evidence(
            True,
            status,
            None,
            "dispositive_local_lemma_order",
            "the local གོང run establishes this exact headword identity",
        ))

    def test_unresolved_root_change_cannot_bypass_guard(self) -> None:
        status = module.root_change_status([
            self.attribution(
                "none", status="structurally_unresolved", extra="no"
            )
        ])
        self.assertEqual(status, "unresolved")
        with self.assertRaises(ValueError):
            module.require_occurrence_identity_evidence(
                True, status, None, None, None
            )
        self.assertTrue(module.require_occurrence_identity_evidence(
            True,
            status,
            "yes",
            "independent_clean_same_tibetan_identity",
            "independent clean identity",
        ))

    def test_unresolved_declared_non_root_is_explicitly_allowed(self) -> None:
        self.assertFalse(module.require_occurrence_identity_evidence(
            True, "unresolved", "no", None, None
        ))


if __name__ == "__main__":
    unittest.main()
